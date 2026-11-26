"""Gemini image models ("Nano Banana") on Vertex AI via generateContent."""

import asyncio

from app.models import MediaType
from app.providers import GeneratedMedia, ProviderError
from app.providers.clients import vertex_client


async def _one(ctx, contents, config) -> GeneratedMedia:
    resp = await vertex_client().aio.models.generate_content(
        model=ctx.spec.model, contents=contents, config=config
    )
    texts = []
    for cand in resp.candidates or []:
        for part in (cand.content.parts if cand.content else None) or []:
            if part.inline_data and part.inline_data.data:
                return GeneratedMedia(
                    part.inline_data.data,
                    part.inline_data.mime_type or "image/png",
                    MediaType.image,
                )
            if part.text:
                texts.append(part.text)
    reason = resp.candidates[0].finish_reason if resp.candidates else None
    detail = " ".join(texts).strip() or (f"finish reason {reason}" if reason else "no reason given")
    raise ProviderError(f"The model didn't return an image ({detail[:300]})")


async def run(ctx) -> list[GeneratedMedia]:
    from google.genai import types

    p = ctx.params
    image_config = {"aspect_ratio": p["aspect_ratio"]} if "aspect_ratio" in p else {}
    if "image_size" in p:
        image_config["image_size"] = p["image_size"]
    config = types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"],
        image_config=types.ImageConfig(**image_config) if image_config else None,
    )
    contents = [
        types.Part.from_bytes(data=data, mime_type=asset.content_type)
        for asset, data in ctx.inputs("image")
    ]
    contents.append(types.Part.from_text(text=ctx.job.prompt or ""))

    await ctx.report_progress(0.1)
    n = int(p.get("n", 1))
    results = await asyncio.gather(
        *(_one(ctx, contents, config) for _ in range(n)), return_exceptions=True
    )
    outputs = [r for r in results if isinstance(r, GeneratedMedia)]
    if not outputs:
        error = next(r for r in results if isinstance(r, BaseException))
        raise error
    return outputs
