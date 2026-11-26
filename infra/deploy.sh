#!/usr/bin/env bash
# Deploys AI Content Studio to Google Cloud Run.
#
# Creates (if missing): Artifact Registry repo, Cloud Storage bucket, Cloud SQL
# Postgres instance, a runtime service account, and three Cloud Run services:
#   studio-api     public HTTPS API
#   studio-worker  background job runner (always-on CPU, not public)
#   studio-web     Next.js site
# plus a Cloud Run job that runs database migrations.
#
# Usage: PROJECT_ID=my-project REGION=us-central1 OPENAI_API_KEY=sk-... FIREBASE_API_KEY=... ./infra/deploy.sh
# Re-running is safe; existing resources are reused.
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
REPO="${REPO:-studio}"
BUCKET="${BUCKET:-${PROJECT_ID}-studio-media}"
SQL_INSTANCE="${SQL_INSTANCE:-studio-db}"
SQL_TIER="${SQL_TIER:-db-g1-small}"
DB_NAME="studio"
SA_NAME="studio-runtime"
SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
TAG="$(git rev-parse --short HEAD 2>/dev/null || date +%s)"
IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

gcloud config set project "$PROJECT_ID" >/dev/null

echo "==> Enabling APIs"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  sqladmin.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com \
  iamcredentials.googleapis.com identitytoolkit.googleapis.com aiplatform.googleapis.com

echo "==> Artifact Registry"
gcloud artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1 ||
  gcloud artifacts repositories create "$REPO" --repository-format docker --location "$REGION"

echo "==> Service account"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 ||
  gcloud iam service-accounts create "$SA_NAME" --display-name "AI Content Studio runtime"
for role in roles/cloudsql.client roles/aiplatform.user roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$SA" \
    --role "$role" --condition None >/dev/null
done
# Lets the service sign Cloud Storage URLs with its own identity.
gcloud iam service-accounts add-iam-policy-binding "$SA" --member "serviceAccount:$SA" \
  --role roles/iam.serviceAccountTokenCreator >/dev/null

echo "==> Storage bucket"
gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 ||
  gcloud storage buckets create "gs://$BUCKET" --location "$REGION" \
    --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member "serviceAccount:$SA" --role roles/storage.objectAdmin >/dev/null

echo "==> Cloud SQL"
if ! gcloud sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
  gcloud sql instances create "$SQL_INSTANCE" --database-version POSTGRES_16 \
    --tier "$SQL_TIER" --region "$REGION" --storage-auto-increase
  gcloud sql databases create "$DB_NAME" --instance "$SQL_INSTANCE"
fi
CONN="$(gcloud sql instances describe "$SQL_INSTANCE" --format 'value(connectionName)')"
if ! gcloud secrets describe studio-database-url >/dev/null 2>&1; then
  DB_PASS="$(openssl rand -hex 24)"
  gcloud sql users create studio --instance "$SQL_INSTANCE" --password "$DB_PASS"
  printf 'postgresql+asyncpg://studio:%s@/%s?host=/cloudsql/%s' "$DB_PASS" "$DB_NAME" "$CONN" |
    gcloud secrets create studio-database-url --data-file=-
fi

echo "==> OpenAI API key"
if ! gcloud secrets describe studio-openai-api-key >/dev/null 2>&1; then
  : "${OPENAI_API_KEY:?Set OPENAI_API_KEY on first deploy (stored in Secret Manager)}"
  printf '%s' "$OPENAI_API_KEY" | gcloud secrets create studio-openai-api-key --data-file=-
fi

echo "==> Stripe (optional; without it customers can't buy credits)"
SECRETS="DATABASE_URL=studio-database-url:latest,OPENAI_API_KEY=studio-openai-api-key:latest"
for pair in "STRIPE_SECRET_KEY:studio-stripe-secret-key" "STRIPE_WEBHOOK_SECRET:studio-stripe-webhook-secret"; do
  var="${pair%%:*}"; name="${pair#*:}"
  if [ -n "${!var:-}" ]; then
    if gcloud secrets describe "$name" >/dev/null 2>&1; then
      printf '%s' "${!var}" | gcloud secrets versions add "$name" --data-file=-
    else
      printf '%s' "${!var}" | gcloud secrets create "$name" --data-file=-
    fi
  fi
  if gcloud secrets describe "$name" >/dev/null 2>&1; then SECRETS="$SECRETS,$var=$name:latest"; fi
done

echo "==> Building images ($TAG)"
gcloud builds submit backend --tag "$IMAGE_BASE/backend:$TAG"

COMMON_ENV="ENV=production,AUTH_MODE=firebase,GCP_PROJECT_ID=$PROJECT_ID,STORAGE_BACKEND=gcs,GCS_BUCKET=$BUCKET"
COMMON_FLAGS=(--region "$REGION" --service-account "$SA" --add-cloudsql-instances "$CONN"
  --set-secrets "$SECRETS")

echo "==> Migrations"
gcloud run jobs deploy studio-migrate --image "$IMAGE_BASE/backend:$TAG" "${COMMON_FLAGS[@]}" \
  --set-env-vars "$COMMON_ENV" --command alembic --args upgrade,head
gcloud run jobs execute studio-migrate --region "$REGION" --wait

echo "==> Worker"
gcloud run deploy studio-worker --image "$IMAGE_BASE/backend:$TAG" "${COMMON_FLAGS[@]}" \
  --set-env-vars "$COMMON_ENV" --no-allow-unauthenticated --ingress internal \
  --min-instances 1 --max-instances 5 --no-cpu-throttling --memory 1Gi --timeout 3600 \
  --command uvicorn --args app.worker.main:app,--host,0.0.0.0,--port,8080

echo "==> API"
WEB_URL="$(gcloud run services describe studio-web --region "$REGION" --format 'value(status.url)' 2>/dev/null || true)"
CORS="${CORS_ORIGINS:-[\"${WEB_URL:-http://localhost:3000}\"]}"
gcloud run deploy studio-api --image "$IMAGE_BASE/backend:$TAG" "${COMMON_FLAGS[@]}" \
  --set-env-vars "^@^${COMMON_ENV//,/@}@CORS_ORIGINS=${CORS}@PUBLIC_WEB_URL=${WEB_URL:-http://localhost:3000}" \
  --allow-unauthenticated --memory 1Gi --timeout 300
API_URL="$(gcloud run services describe studio-api --region "$REGION" --format 'value(status.url)')"

echo "==> Web"
: "${FIREBASE_API_KEY:?Set FIREBASE_API_KEY (Identity Platform > Application setup details)}"
AUTH_DOMAIN="${FIREBASE_AUTH_DOMAIN:-${PROJECT_ID}.firebaseapp.com}"
gcloud builds submit frontend --config /dev/stdin <<YAML
steps:
- name: gcr.io/cloud-builders/docker
  args: [build, -t, "$IMAGE_BASE/web:$TAG",
         --build-arg, "NEXT_PUBLIC_API_URL=$API_URL",
         --build-arg, "NEXT_PUBLIC_AUTH_MODE=firebase",
         --build-arg, "NEXT_PUBLIC_FIREBASE_API_KEY=$FIREBASE_API_KEY",
         --build-arg, "NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=$AUTH_DOMAIN",
         --build-arg, "NEXT_PUBLIC_FIREBASE_PROJECT_ID=$PROJECT_ID", "."]
images: ["$IMAGE_BASE/web:$TAG"]
YAML
gcloud run deploy studio-web --image "$IMAGE_BASE/web:$TAG" --region "$REGION" \
  --allow-unauthenticated --memory 512Mi
WEB_URL="$(gcloud run services describe studio-web --region "$REGION" --format 'value(status.url)')"

# Point the API's CORS and Stripe return URLs at the real site (first deploy doesn't know it yet).
gcloud run services update studio-api --region "$REGION" \
  --update-env-vars "^@^CORS_ORIGINS=[\"$WEB_URL\"]@PUBLIC_WEB_URL=$WEB_URL" >/dev/null

echo
echo "Done."
echo "  Web: $WEB_URL"
echo "  API: $API_URL"
echo "Stripe webhook endpoint: $API_URL/v1/billing/stripe/webhook"
echo "  (events: checkout.session.completed, checkout.session.async_payment_succeeded)"
echo "Add $(echo "$WEB_URL" | sed 's|https://||') to Identity Platform > Settings > Authorized domains."
