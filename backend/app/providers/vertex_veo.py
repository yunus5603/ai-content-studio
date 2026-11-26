"""Veo video models on Vertex AI (long-running operations)."""

import asyncio
import time

from app.core.config import get_settings
from app.models import MediaType
from app.providers import GeneratedMedia, ProviderError
from app.providers.clients import vertex_client

POLL_SECONDS = 10
# Typical generation time, used only to show a progress estimate.
EXPECTED_SECONDS = 120

_CONFIG_KEYS = [
    "number_of_videos",
    "duration_seconds",
    "aspect_ratio",
    "resolution",
    "generate_audio",
    "negative_prompt",
    "seed",
    "person_generation",
]


async def _download(video) -> bytes:
    if video.video_bytes:
        return video.video_bytes
    if video.uri and video.uri.startswith("gs://"):
        from google.cloud import storage

        bucket, _, key = video.uri.removeprefix("gs://").partition("/")
        client = storage.Client(project=get_settings().gcp_project_id)
        return await asyncio.to_thread(client.bucket(bucket).blob(key).download_as_bytes)
    raise ProviderError("Veo returned a video we couldn't download")


async def run(ctx) -> list[GeneratedMedia]:
    from google.genai import types

    settings = get_settings()
    client = vertex_client(settings.vertex_video_location)
    p = ctx.params

    if ctx.job.external_id:
        # A previous attempt already started this video; resume instead of paying twice.
        operation = types.GenerateVideosOperation(name=ctx.job.external_id)
        operation = await client.aio.operations.get(operation)
    else:
        config = {k: p[k] for k in _CONFIG_KEYS if k in p}
        if settings.storage_backend == "gcs" and settings.gcs_bucket:
            config["output_gcs_uri"] = f"gs://{settings.gcs_bucket}/provider-tmp/veo/{ctx.job.id}/"
        image = None
        if ctx.job.operation == "image_to_video":
            [(first, first_data)] = ctx.inputs("first_frame")
            image = types.Image(image_bytes=first_data, mime_type=first.content_type)
            last = ctx.inputs("last_frame")
            if last:
                config["last_frame"] = types.Image(
                    image_bytes=last[0][1], mime_type=last[0][0].content_type
                )
        operation = await client.aio.models.generate_videos(
            model=ctx.spec.model,
            source=types.GenerateVideosSource(prompt=ctx.job.prompt or "", image=image),
            config=types.GenerateVideosConfig(**config),
        )
        await ctx.set_external_id(operation.name)

    started = time.monotonic()
    while not operation.done:
        await asyncio.sleep(POLL_SECONDS)
        operation = await client.aio.operations.get(operation)
        await ctx.report_progress(min(0.95, (time.monotonic() - started) / EXPECTED_SECONDS))
        if await ctx.is_canceled():
            return []

    if operation.error:
        message = operation.error.get("message") if isinstance(operation.error, dict) else None
        raise ProviderError(f"Veo failed: {message or operation.error}")
    response = operation.response or operation.result
    videos = (response.generated_videos if response else None) or []
    if not videos:
        reasons = (response.rai_media_filtered_reasons if response else None) or []
        raise ProviderError(
            "Veo blocked the video" + (f": {'; '.join(reasons)}" if reasons else "")
        )

    width_height = {
        ("16:9", "720p"): (1280, 720),
        ("16:9", "1080p"): (1920, 1080),
        ("9:16", "720p"): (720, 1280),
        ("9:16", "1080p"): (1080, 1920),
    }
    w, h = width_height.get((p.get("aspect_ratio"), p.get("resolution")), (None, None))
    return [
        GeneratedMedia(
            await _download(gv.video),
            gv.video.mime_type or "video/mp4",
            MediaType.video,
            w,
            h,
            float(p.get("duration_seconds", 0)) or None,
        )
        for gv in videos
        if gv.video
    ]
