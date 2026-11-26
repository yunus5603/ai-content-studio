"""Check that every catalog model is reachable with our credentials. Costs nothing.

    uv run python -m scripts.check_models

Uses OPENAI_API_KEY and GCP_PROJECT_ID / application default credentials.
"""

import asyncio

from app.catalog import load_catalog
from app.core.config import get_settings
from app.providers.clients import openai_client, vertex_client


async def check(model) -> tuple[str, bool, str]:
    try:
        if model.provider == "openai":
            await openai_client().models.retrieve(model.model)
        elif model.provider == "vertex":
            location = get_settings().vertex_video_location if model.media_type == "video" else None
            await vertex_client(location).aio.models.get(model=model.model)
        return model.id, True, "ok"
    except Exception as exc:  # report and continue
        return model.id, False, f"{type(exc).__name__}: {str(exc)[:160]}"


async def main() -> None:
    results = await asyncio.gather(*(check(m) for m in load_catalog().values()))
    for model_id, ok, detail in results:
        print(f"{'OK ' if ok else 'ERR'}  {model_id:45} {detail}")
    failed = [r for r in results if not r[1]]
    if failed:
        print(
            f"\n{len(failed)} model(s) unreachable. Disable them in app/catalog/models.yaml "
            "(enabled: false) or fix the model id."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
