# Roadmap

The first version is built in four steps. Each lands as its own pull request.

1. **Foundation** (done)
   Landing page and app shell (Next.js), Python API (FastAPI), Postgres, Cloud Storage,
   a Postgres-backed job queue and worker, Google Identity Platform sign-in, and
   workspaces with Owner / Admin / Member / Viewer roles. Deploys to Cloud Run.

2. **Generation engine** (done)
   A config-driven model catalog covering every image and video model in OpenAI
   (GPT Image) and Vertex AI (Gemini image, Veo), with the parameters each one
   supports. The UI builds its controls from the catalog. Text to image, image
   edit and inpainting, text to video, image to video, prompt enhancement, live
   job progress, share links.

3. **Usage and billing** (done)
   Per-job metering at the provider's price plus a 10% platform fee. Free credits
   on sign-up, then Stripe checkout for credit packs. Holds at submit and settlement
   at finish, refunds for failures, monthly limits per workspace and per member,
   usage reports, and a staff admin page.

4. **Copilot** (done)
   An assistant that turns a rough idea into a plan: improves the prompt, picks
   models and settings, chains steps (image, then animate), shows the estimated
   cost and asks before spending.

**Storyboards** (added alongside step 4)
   Plan a sequence shot by shot: what each frame shows, what happens in it, length,
   and reference images for consistent characters or products. Each shot gets a
   keyframe image, then is animated from that keyframe (optionally ending on the next
   shot's keyframe), and the clips are joined into one film with cuts or crossfades.
   Every step is an ordinary job, priced up front and billed like anything else;
   assembling the film is free.
