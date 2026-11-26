# AI Content Studio

A web app for generating images and videos with OpenAI and Google Vertex AI models.
Customers sign up, get free credits, work in shared team workspaces, and pay per
generation after that. See [docs/ROADMAP.md](docs/ROADMAP.md) for the build plan.

## Architecture

```
 Browser ──▶ studio-web (Next.js)          Cloud Run
    │
    └──────▶ studio-api (FastAPI) ──┐      Cloud Run, public
                                    ├──▶ Postgres (Cloud SQL)
             studio-worker ─────────┘      Cloud Run, always-on, internal
                  │    ▲ claims queued jobs (SELECT … FOR UPDATE SKIP LOCKED)
                  ▼    │
          OpenAI / Vertex AI          Cloud Storage (uploads + outputs, signed URLs)
```

- **Auth**: Google Identity Platform (Firebase Auth). The browser signs in and sends an
  ID token; the API verifies it and creates the user plus a personal workspace on first visit.
- **Workspaces and roles**: every resource belongs to a workspace. Roles are ordered
  `viewer < member < admin < owner`; see `backend/app/core/permissions.py`.
  - viewer: browse gallery, jobs, members
  - member: also upload and generate
  - admin: also invite, remove, change roles (cannot touch the owner)
  - owner: also rename/delete the workspace and manage billing
- **Jobs**: a generation request is a row in `jobs`. Workers claim rows with
  `SKIP LOCKED`, so you can run many workers without a separate queue service. A running
  job sends heartbeats; if a worker dies, the job is retried up to `JOB_MAX_ATTEMPTS`.
  Outputs are saved to storage and the gallery automatically.
- **Uploads**: file type is detected from content, not the filename. Images and videos
  up to `MAX_UPLOAD_BYTES` (500 MB default).

## Repository layout

```
backend/    FastAPI API + worker (Python 3.12+, uv, SQLAlchemy, Alembic)
frontend/   Next.js app router + Tailwind (landing page, sign-in, studio)
infra/      Cloud Run deploy script
docs/       Roadmap
```

## Run locally

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22, Postgres 16
(or Docker).

**With Docker:** `docker compose up --build`, then open http://localhost:3000.

**Without Docker:**

```bash
# Backend
cd backend
cp .env.example .env            # edit DATABASE_URL if needed
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000          # API
uv run uvicorn app.worker.main:app --port 8081            # worker (second terminal)

# Frontend
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Local mode uses **dev auth** (sign in with any email, no password) and stores media in
`backend/.media`. With `ENABLE_DEBUG_OPERATIONS=true` the model picker also offers
**Debug pixel** (instant placeholder images) and **Debug clip** (a simulated video job,
needs ffmpeg), so you can try every screen without spending provider credits.

To use real models locally, set `OPENAI_API_KEY`, `GCP_PROJECT_ID` and sign in to Google
Cloud (`gcloud auth application-default login`). Check that every catalog model is
reachable with `uv run python -m scripts.check_models`.

## Models

The model list lives in `backend/app/catalog/models.yaml`: each model's operations,
parameters (the UI builds its controls from these), validation rules and prices. Add,
retire or re-price a model there; no code change needed for a new model on an existing
adapter. Prices marked `verified: false` came from secondary sources and must be checked
against the provider price lists before billing customers (step 3).

As of November 2026: OpenAI GPT Image 2.6 / 2.5 / 2 for images (Sora was shut down in
September 2026), Google Gemini image models (Nano Banana 2.1, 3.1 Flash, 3 Pro, Flash Lite)
and Veo 3.1 / Fast / Lite for video.

### Tests

```bash
cd backend && createdb studio_test && uv run pytest
cd frontend && npm run lint && npm run build
```

## Deploy to Google Cloud

1. In the Google Cloud console, enable **Identity Platform** and turn on the Google and
   Email/Password providers. Copy the Web API key.
2. Run:

   ```bash
   PROJECT_ID=your-project REGION=us-central1 OPENAI_API_KEY=sk-... FIREBASE_API_KEY=... ./infra/deploy.sh
   ```

   This creates the bucket, Cloud SQL database, service account, runs migrations, and
   deploys `studio-api`, `studio-worker` and `studio-web`. It is safe to re-run.
3. Add the printed web domain to Identity Platform's authorized domains.

Production refuses to start with dev auth or local storage.

## Configuration

All backend settings are environment variables; see `backend/app/core/config.py` and
`backend/.env.example`. Frontend settings are `NEXT_PUBLIC_*` variables in
`frontend/.env.example` (baked in at build time).
