"""Storyboards: turn shots into keyframe and clip jobs, and fold finished jobs back in.

Each shot goes keyframe (image job) -> clip (image-to-video job from the keyframe),
then all clips are joined by the internal `studio/stitch` job. Every step is an
ordinary job, so it gets the same validation, holds, refunds and gallery saving
as anything made in the studio.
"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import load_catalog
from app.catalog.schema import ModelSpec
from app.core.config import Settings
from app.models import Asset, Job, JobStatus, MediaType, Shot, Storyboard
from app.models.billing import to_usd
from app.services.generation import GenerationError, price_of, resolve

STITCH_MODEL = "studio/stitch"
DEFAULT_IMAGE_MODELS = ["vertex/gemini-nano-banana-2.1", "openai/gpt-image-2.6-sunburst"]
DEFAULT_VIDEO_MODELS = ["vertex/veo-3.1-fast-generate-001", "vertex/veo-3.1-generate-001"]


def _first_supporting(settings: Settings, preferred: list[str], operation: str) -> str:
    catalog = load_catalog(include_debug=settings.enable_debug_operations)
    for model_id in preferred:
        if model_id in catalog and catalog[model_id].operation(operation):
            return model_id
    for spec in catalog.values():
        if spec.operation(operation):
            return spec.id
    raise GenerationError("No model in the catalog can do this")


def default_image_model(settings: Settings) -> str:
    return _first_supporting(settings, DEFAULT_IMAGE_MODELS, "text_to_image")


def default_video_model(settings: Settings) -> str:
    return _first_supporting(settings, DEFAULT_VIDEO_MODELS, "image_to_video")


def widescreen_defaults(spec: ModelSpec) -> dict[str, Any]:
    """Storyboards default to landscape frames where the model offers them."""
    out: dict[str, Any] = {}
    for p in spec.params:
        values = {o.value for o in p.options}
        if p.name == "aspect_ratio" and "16:9" in values:
            out[p.name] = "16:9"
        elif p.name == "size" and "1536x1024" in values:
            out[p.name] = "1536x1024"
    return out


def _params_for(spec: ModelSpec, operation: str, base: dict[str, Any]) -> dict[str, Any]:
    """Storyboard-level params narrowed to what this operation accepts, one output per job."""
    names = {p.name for p in spec.params_for(operation)}
    params = {k: v for k, v in (base or {}).items() if k in names}
    if spec.pricing.quantity_param and spec.pricing.quantity_param in names:
        params[spec.pricing.quantity_param] = 1
    return params


def keyframe_prompt(sb: Storyboard, shot: Shot) -> str:
    parts = [shot.description.strip() or shot.title or sb.title]
    if sb.style:
        parts.append(f"Style: {sb.style.strip()}")
    return "\n\n".join(parts)


def clip_prompt(sb: Storyboard, shot: Shot) -> str:
    parts = [(shot.motion or "").strip() or shot.description.strip() or shot.title or sb.title]
    if shot.motion and shot.description:
        parts.append(f"Scene: {shot.description.strip()}")
    if sb.style:
        parts.append(f"Style: {sb.style.strip()}")
    return "\n\n".join(parts)


class JobPlan:
    """A job ready to submit: model, operation, prompt, params, inputs."""

    def __init__(self, model: str, operation: str, prompt: str, params: dict, inputs: list):
        self.model = model
        self.operation = operation
        self.prompt = prompt
        self.params = params
        self.inputs = inputs


def keyframe_plan(settings: Settings, sb: Storyboard, shot: Shot, live_refs: list[str]) -> JobPlan:
    spec, _ = resolve(settings, sb.image_model, "text_to_image", {})
    operation = "text_to_image"
    inputs: list[dict[str, str]] = []
    if live_refs:
        edit = spec.operation("image_edit")
        if edit is None:
            raise GenerationError(f"{spec.name} can't use reference images; pick another model")
        rule = next((i for i in edit.inputs if i.role == "image"), None)
        if rule is None or len(live_refs) > rule.max:
            raise GenerationError(f"{spec.name} takes at most {rule.max if rule else 0} references")
        operation = "image_edit"
        inputs = [{"asset_id": a, "role": "image"} for a in live_refs]
    params = _params_for(spec, operation, sb.image_params)
    return JobPlan(spec.id, operation, keyframe_prompt(sb, shot), params, inputs)


def clip_plan(settings: Settings, sb: Storyboard, shot: Shot, next_shot: Shot | None) -> JobPlan:
    if shot.keyframe_asset_id is None:
        raise GenerationError("Make a keyframe first")
    spec, _ = resolve(settings, sb.video_model, "image_to_video", {})
    op = spec.operation("image_to_video")
    if op is None:
        raise GenerationError(f"{spec.name} can't animate images; pick another video model")
    params = _params_for(spec, "image_to_video", sb.video_params)
    seconds = spec.pricing.seconds_param
    if shot.duration_seconds and seconds:
        params[seconds] = shot.duration_seconds
    inputs = [{"asset_id": str(shot.keyframe_asset_id), "role": "first_frame"}]
    if (
        shot.end_on_next
        and next_shot is not None
        and next_shot.keyframe_asset_id is not None
        and any(i.role == "last_frame" for i in op.inputs)
    ):
        inputs.append({"asset_id": str(next_shot.keyframe_asset_id), "role": "last_frame"})
    return JobPlan(spec.id, "image_to_video", clip_prompt(sb, shot), params, inputs)


def plan_price(settings: Settings, plan: JobPlan, internal: bool = False) -> float:
    spec, params = resolve(settings, plan.model, plan.operation, plan.params, internal=internal)
    return price_of(spec, params)


def duration_of(settings: Settings, sb: Storyboard, shot: Shot) -> float:
    """Clip length in seconds with the current settings (0 if unknown)."""
    if shot.duration_seconds:
        return float(shot.duration_seconds)
    try:
        spec, _ = resolve(settings, sb.video_model, "image_to_video", {})
        key = spec.pricing.seconds_param
        if not key:
            return 0.0
        _, params = resolve(
            settings,
            spec.id,
            "image_to_video",
            _params_for(spec, "image_to_video", sb.video_params),
        )
        return float(params.get(key, 0))
    except GenerationError:
        return 0.0


async def sync(session: AsyncSession, sb: Storyboard) -> dict[uuid.UUID, Job]:
    """Fold finished jobs into the storyboard. Returns the jobs still referenced."""
    ids = {j for s in sb.shots for j in (s.keyframe_job_id, s.clip_job_id) if j is not None}
    if sb.film_job_id:
        ids.add(sb.film_job_id)
    if not ids:
        return {}
    jobs = {j.id: j for j in await session.scalars(select(Job).where(Job.id.in_(ids)))}
    done = [j.id for j in jobs.values() if j.status == JobStatus.succeeded]
    outputs: dict[uuid.UUID, Asset] = {}
    if done:
        for a in await session.scalars(
            select(Asset).where(Asset.job_id.in_(done)).order_by(Asset.created_at.desc())
        ):
            outputs[a.job_id] = a  # earliest output wins (iterating newest first)

    changed = False
    for shot in sb.shots:
        job = jobs.get(shot.keyframe_job_id)
        if job and job.status == JobStatus.succeeded:
            if job.id in outputs:
                shot.keyframe_asset_id = outputs[job.id].id
            shot.keyframe_job_id = None
            changed = True
        job = jobs.get(shot.clip_job_id)
        if job and job.status == JobStatus.succeeded:
            if job.id in outputs:
                shot.clip_asset_id = outputs[job.id].id
                first = next((i for i in job.inputs if i["role"] == "first_frame"), None)
                shot.clip_keyframe_id = uuid.UUID(first["asset_id"]) if first else None
            shot.clip_job_id = None
            changed = True
    job = jobs.get(sb.film_job_id)
    if job and job.status == JobStatus.succeeded:
        if job.id in outputs:
            sb.film_asset_id = outputs[job.id].id
            sb.film_source = [i["asset_id"] for i in job.inputs]
        sb.film_job_id = None
        changed = True
    if changed:
        await session.flush()
    return {k: v for k, v in jobs.items() if v.status != JobStatus.succeeded}


async def spent(session: AsyncSession, sb: Storyboard) -> float:
    micros = await session.scalar(
        select(
            func.coalesce(func.sum(func.coalesce(Job.charged_micros, Job.hold_micros)), 0)
        ).where(Job.storyboard_id == sb.id)
    )
    return to_usd(int(micros))


async def live_assets(
    session: AsyncSession, workspace_id: uuid.UUID, ids: set[uuid.UUID]
) -> dict[uuid.UUID, Asset]:
    if not ids:
        return {}
    return {
        a.id: a
        for a in await session.scalars(
            select(Asset).where(Asset.id.in_(ids), Asset.workspace_id == workspace_id)
        )
    }


async def check_references(
    session: AsyncSession, workspace_id: uuid.UUID, ids: list[uuid.UUID]
) -> list[str]:
    found = await live_assets(session, workspace_id, set(ids))
    if len(found) != len(set(ids)) or any(a.media_type != MediaType.image for a in found.values()):
        raise GenerationError("References must be images from this workspace")
    return [str(i) for i in dict.fromkeys(ids)]
