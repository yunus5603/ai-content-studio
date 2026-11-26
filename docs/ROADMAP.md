# Roadmap

The first version is built in four steps. Each lands as its own pull request.

1. **Foundation** (this PR)
   Landing page and app shell (Next.js), Python API (FastAPI), Postgres, Cloud Storage,
   a Postgres-backed job queue and worker, Google Identity Platform sign-in, and
   workspaces with Owner / Admin / Member / Viewer roles. Deploys to Cloud Run.

2. **Generation engine**
   A config-driven model catalog covering every image and video model in OpenAI
   (GPT Image, Sora) and Vertex AI (Imagen, Veo), with the parameters each one
   supports. The UI builds its controls from the catalog. Text to image, image
   edit and inpainting, text to video, image to video, prompt enhancement, live
   job progress, share links.

3. **Usage and billing**
   Per-job metering at the provider's price plus a 10% platform fee. Free credits
   on sign-up, then Stripe checkout for credit packs. Spending limits and an
   admin dashboard.

4. **Copilot**
   An assistant that turns a rough idea into a plan: improves the prompt, picks
   models and settings, chains steps (image, then animate), shows the estimated
   cost and asks before spending.
