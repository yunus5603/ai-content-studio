"""OpenAI GPT Image models via the Images API (generations and edits)."""

import base64
import logging

from app.models import MediaType
from app.providers import GeneratedMedia, ProviderError, size_of
from app.providers.clients import openai_client

log = logging.getLogger(__name__)

_CONTENT_TYPES = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}
_PASSTHROUGH = [
    "quality",
    "size",
    "n",
    "output_format",
    "background",
    "output_compression",
    "moderation",
    "complexity",
    "frame_count",
    "frame_duration_ms",
]


async def run(ctx) -> list[GeneratedMedia]:
    import openai

    p = ctx.params
    args = {k: p[k] for k in _PASSTHROUGH if k in p}
    args["model"] = ctx.spec.model
    args["prompt"] = ctx.job.prompt or ""
    args["safety_identifier"] = str(ctx.job.created_by_id)
    client = openai_client()
    await ctx.report_progress(0.1)
    try:
        if ctx.job.operation == "text_to_image":
            resp = await client.images.generate(**args)
        else:
            images = [
                (a.filename or f"image{i}.png", data, a.content_type)
                for i, (a, data) in enumerate(ctx.inputs("image"))
            ]
            if "input_fidelity" in p:
                args["input_fidelity"] = p["input_fidelity"]
            if ctx.job.operation == "inpaint":
                [(mask, mask_data)] = ctx.inputs("mask")
                args["mask"] = ("mask.png", mask_data, mask.content_type)
            resp = await client.images.edit(image=images, **args)
    except openai.BadRequestError as exc:
        # Content policy rejections and invalid parameter combinations land here.
        message = getattr(exc, "message", None) or str(exc)
        raise ProviderError(f"OpenAI rejected the request: {message}") from exc

    usage = getattr(resp, "usage", None)
    if usage is not None:
        details = getattr(usage, "input_tokens_details", None)
        ctx.usage = {
            "text_input_tokens": getattr(details, "text_tokens", 0) or 0,
            "image_input_tokens": getattr(details, "image_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        }

    fmt = p.get("output_format", "png")
    width, height = size_of(p.get("size"))
    outputs = [
        GeneratedMedia(
            base64.b64decode(item.b64_json),
            _CONTENT_TYPES.get(fmt, "image/png"),
            MediaType.image,
            width,
            height,
        )
        for item in resp.data or []
        if item.b64_json
    ]
    if not outputs:
        raise ProviderError("OpenAI returned no images")
    return outputs
