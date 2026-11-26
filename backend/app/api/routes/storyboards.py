import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import workspace_access
from app.api.routes.assets import asset_out
from app.catalog.pricing import with_fee
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.permissions import Action
from app.models import Asset, Job, JobStatus, MediaType, Shot, Storyboard
from app.models.billing import to_usd
from app.schemas.storyboard import (
    GenerateRequest,
    JobBrief,
    KeyframePick,
    ShotCreate,
    ShotOrder,
    ShotOut,
    ShotUpdate,
    StepCost,
    StoryboardCreate,
    StoryboardOut,
    StoryboardSummary,
    StoryboardTotals,
    StoryboardUpdate,
)
from app.services import generation
from app.services import storyboards as svc
from app.services.generation import GenerationError
from app.services.storage import Storage, get_storage
from app.services.workspaces import WorkspaceAccess

router = APIRouter(prefix="/workspaces/{workspace_id}/storyboards", tags=["storyboards"])

MAX_SHOTS = 60


def _fail(exc: GenerationError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


def _brief(job: Job | None) -> JobBrief | None:
    if job is None:
        return None
    price = (
        to_usd(job.charged_micros)
        if job.charged_micros is not None
        else (to_usd(job.hold_micros) if job.hold_micros else with_fee(job.estimated_cost_usd))
    )
    return JobBrief(
        id=job.id, status=job.status, progress=job.progress, error=job.error, price_usd=price
    )


async def _load(session: AsyncSession, access: WorkspaceAccess, sb_id: uuid.UUID) -> Storyboard:
    sb = await session.scalar(
        select(Storyboard)
        .where(Storyboard.id == sb_id)
        .options(selectinload(Storyboard.shots))
        .execution_options(populate_existing=True)
    )
    if sb is None or sb.workspace_id != access.workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Storyboard not found")
    return sb


def _shot(sb: Storyboard, shot_id: uuid.UUID) -> Shot:
    shot = next((s for s in sb.shots if s.id == shot_id), None)
    if shot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shot not found")
    return shot


def _renumber(shots: list[Shot]) -> None:
    for i, s in enumerate(shots):
        s.position = i


def _touch(sb: Storyboard) -> None:
    sb.updated_at = datetime.now(UTC)


def _check_models(settings: Settings, sb: Storyboard) -> None:
    """Both models must exist and do their step; params must validate."""
    try:
        img, _ = generation.resolve(settings, sb.image_model, "text_to_image", {})
        generation.resolve(
            settings,
            img.id,
            "text_to_image",
            svc._params_for(img, "text_to_image", sb.image_params),
        )
        vid = generation.resolve(settings, sb.video_model, "image_to_video", {})[0]
        generation.resolve(
            settings,
            vid.id,
            "image_to_video",
            svc._params_for(vid, "image_to_video", sb.video_params),
        )
    except GenerationError as exc:
        raise _fail(exc) from exc
    if img.media_type != "image" or vid.media_type != "video":
        raise HTTPException(422, "Pick an image model for keyframes and a video model for clips")


async def _render(
    session: AsyncSession, sb: Storyboard, storage: Storage, settings: Settings
) -> StoryboardOut:
    jobs = await svc.sync(session, sb)
    await session.commit()
    shots = sb.shots
    wanted: set[uuid.UUID] = set()
    for s in shots:
        wanted |= {uuid.UUID(r) for r in s.reference_asset_ids or []}
        wanted |= {i for i in (s.keyframe_asset_id, s.clip_asset_id) if i}
    if sb.film_asset_id:
        wanted.add(sb.film_asset_id)
    assets = await svc.live_assets(session, sb.workspace_id, wanted)
    outs = {i: await asset_out(a, storage) for i, a in assets.items()}

    totals = StoryboardTotals(
        shots=len(shots),
        keyframes_done=0,
        clips_done=0,
        seconds=0.0,
        missing_keyframes_usd=0.0,
        missing_clips_usd=0.0,
        all_keyframes_usd=0.0,
        all_clips_usd=0.0,
        spent_usd=await svc.spent(session, sb),
    )
    shot_outs = []
    for idx, s in enumerate(shots):
        refs = [r for r in s.reference_asset_ids or [] if uuid.UUID(r) in assets]
        has_kf = s.keyframe_asset_id in outs
        has_clip = s.clip_asset_id in outs
        try:
            kf_cost = StepCost(
                price_usd=svc.plan_price(settings, svc.keyframe_plan(settings, sb, s, refs))
            )
        except GenerationError as exc:
            kf_cost = StepCost(price_usd=None, problem=str(exc))
        try:
            # Price the clip even before the keyframe exists, so totals are useful up front.
            plan = svc.clip_plan(settings, sb, s if has_kf else _with_fake_keyframe(s), None)
            clip_cost = StepCost(price_usd=svc.plan_price(settings, plan))
            if not has_kf:
                clip_cost.problem = "Make a keyframe first"
        except GenerationError as exc:
            clip_cost = StepCost(price_usd=None, problem=str(exc))
        stale = has_clip and s.clip_keyframe_id != s.keyframe_asset_id
        totals.keyframes_done += has_kf
        totals.clips_done += has_clip
        totals.seconds += svc.duration_of(settings, sb, s)
        kp, cp = kf_cost.price_usd or 0.0, clip_cost.price_usd or 0.0
        totals.all_keyframes_usd += kp
        totals.all_clips_usd += cp
        if not has_kf:
            totals.missing_keyframes_usd += kp
        if not has_clip or stale:
            totals.missing_clips_usd += cp
        shot_outs.append(
            ShotOut(
                id=s.id,
                position=idx,
                title=s.title,
                description=s.description,
                motion=s.motion,
                duration_seconds=s.duration_seconds,
                end_on_next=s.end_on_next,
                references=[outs[uuid.UUID(r)] for r in refs],
                keyframe=outs.get(s.keyframe_asset_id),
                keyframe_job=_brief(jobs.get(s.keyframe_job_id)),
                clip=outs.get(s.clip_asset_id),
                clip_job=_brief(jobs.get(s.clip_job_id)),
                clip_stale=stale,
                keyframe_cost=kf_cost,
                clip_cost=clip_cost,
            )
        )
    for f in (
        "missing_keyframes_usd",
        "missing_clips_usd",
        "all_keyframes_usd",
        "all_clips_usd",
    ):
        setattr(totals, f, round(getattr(totals, f), 6))
    film = outs.get(sb.film_asset_id)
    current = [str(s.clip_asset_id) for s in shots if s.clip_asset_id]
    return StoryboardOut(
        id=sb.id,
        workspace_id=sb.workspace_id,
        created_by_id=sb.created_by_id,
        title=sb.title,
        logline=sb.logline,
        style=sb.style,
        image_model=sb.image_model,
        image_params=sb.image_params or {},
        video_model=sb.video_model,
        video_params=sb.video_params or {},
        transition=sb.transition,
        created_at=sb.created_at,
        updated_at=sb.updated_at,
        shots=shot_outs,
        film=film,
        film_job=_brief(jobs.get(sb.film_job_id)),
        film_stale=bool(film) and (sb.film_source or []) != current,
        totals=totals,
    )


def _with_fake_keyframe(shot: Shot) -> Shot:
    """A detached copy of the shot with a placeholder keyframe, for pricing only."""
    return Shot(
        id=shot.id,
        description=shot.description,
        motion=shot.motion,
        title=shot.title,
        duration_seconds=shot.duration_seconds,
        end_on_next=False,
        keyframe_asset_id=uuid.UUID(int=0),
        reference_asset_ids=[],
    )


# --------------------------------------------------------------------------- storyboards


@router.get("", response_model=list[StoryboardSummary])
async def list_storyboards(
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    access.require(Action.view)
    rows = (
        await session.scalars(
            select(Storyboard)
            .where(Storyboard.workspace_id == access.workspace.id)
            .options(selectinload(Storyboard.shots))
            .order_by(Storyboard.updated_at.desc())
            .limit(200)
        )
    ).all()
    for sb in rows:
        await svc.sync(session, sb)
    await session.commit()
    covers = {s.keyframe_asset_id for sb in rows for s in sb.shots if s.keyframe_asset_id}
    assets = await svc.live_assets(session, access.workspace.id, covers)
    out = []
    for sb in rows:
        cover_id = next(
            (s.keyframe_asset_id for s in sb.shots if s.keyframe_asset_id in assets), None
        )
        out.append(
            StoryboardSummary(
                id=sb.id,
                title=sb.title,
                logline=sb.logline,
                shot_count=len(sb.shots),
                keyframes_done=sum(1 for s in sb.shots if s.keyframe_asset_id),
                clips_done=sum(1 for s in sb.shots if s.clip_asset_id),
                cover=await asset_out(assets[cover_id], storage) if cover_id else None,
                has_film=sb.film_asset_id is not None,
                updated_at=sb.updated_at,
            )
        )
    return out


@router.post("", response_model=StoryboardOut, status_code=201)
async def create_storyboard(
    body: StoryboardCreate,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    access.require(Action.generate)
    try:
        image_model = body.image_model or svc.default_image_model(settings)
        video_model = body.video_model or svc.default_video_model(settings)
        img = generation.resolve(settings, image_model, "text_to_image", {})[0]
        vid = generation.resolve(settings, video_model, "image_to_video", {})[0]
    except GenerationError as exc:
        raise _fail(exc) from exc
    sb = Storyboard(
        id=uuid.uuid4(),
        workspace_id=access.workspace.id,
        created_by_id=access.user.id,
        title=body.title,
        logline=body.logline,
        style=body.style,
        image_model=img.id,
        image_params=body.image_params
        if body.image_params is not None
        else svc.widescreen_defaults(img),
        video_model=vid.id,
        video_params=body.video_params
        if body.video_params is not None
        else svc.widescreen_defaults(vid),
        transition=body.transition,
    )
    _check_models(settings, sb)
    session.add(sb)
    await session.flush()
    for i, s in enumerate(body.shots):
        try:
            refs = await svc.check_references(session, access.workspace.id, s.reference_asset_ids)
        except GenerationError as exc:
            raise _fail(exc) from exc
        session.add(
            Shot(
                storyboard_id=sb.id,
                position=i,
                title=s.title,
                description=s.description,
                motion=s.motion,
                duration_seconds=s.duration_seconds,
                reference_asset_ids=refs,
                end_on_next=s.end_on_next,
            )
        )
    await session.commit()
    return await _render(session, await _load(session, access, sb.id), storage, settings)


@router.get("/{storyboard_id}", response_model=StoryboardOut)
async def get_storyboard(
    storyboard_id: uuid.UUID,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    access.require(Action.view)
    return await _render(session, await _load(session, access, storyboard_id), storage, settings)


@router.patch("/{storyboard_id}", response_model=StoryboardOut)
async def update_storyboard(
    storyboard_id: uuid.UUID,
    body: StoryboardUpdate,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    access.require(Action.generate)
    sb = await _load(session, access, storyboard_id)
    changes = body.model_dump(exclude_unset=True)
    for key in ("title", "transition"):
        if changes.get(key) is not None:
            setattr(sb, key, changes[key])
    for key in ("logline", "style"):
        if key in changes:
            setattr(sb, key, changes[key] or None)
    try:
        # Switching model resets its params to sensible defaults unless new ones are sent.
        if changes.get("image_model") and changes["image_model"] != sb.image_model:
            spec = generation.resolve(settings, changes["image_model"], "text_to_image", {})[0]
            sb.image_model = spec.id
            sb.image_params = svc.widescreen_defaults(spec)
        if changes.get("video_model") and changes["video_model"] != sb.video_model:
            spec = generation.resolve(settings, changes["video_model"], "image_to_video", {})[0]
            sb.video_model = spec.id
            sb.video_params = svc.widescreen_defaults(spec)
    except GenerationError as exc:
        raise _fail(exc) from exc
    if changes.get("image_params") is not None:
        sb.image_params = changes["image_params"]
    if changes.get("video_params") is not None:
        sb.video_params = changes["video_params"]
    _check_models(settings, sb)
    _touch(sb)
    await session.commit()
    return await _render(session, await _load(session, access, sb.id), storage, settings)


@router.delete("/{storyboard_id}", status_code=204)
async def delete_storyboard(
    storyboard_id: uuid.UUID,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
):
    """Deletes the plan only. Keyframes, clips and films stay in the gallery."""
    sb = await _load(session, access, storyboard_id)
    if sb.created_by_id != access.user.id:
        access.require(Action.manage_members)
    else:
        access.require(Action.generate)
    await session.delete(sb)
    await session.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------- shots


@router.post("/{storyboard_id}/shots", response_model=StoryboardOut, status_code=201)
async def add_shot(
    storyboard_id: uuid.UUID,
    body: ShotCreate,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    access.require(Action.generate)
    sb = await _load(session, access, storyboard_id)
    if len(sb.shots) >= MAX_SHOTS:
        raise HTTPException(422, f"A storyboard can have up to {MAX_SHOTS} shots")
    try:
        refs = await svc.check_references(session, access.workspace.id, body.reference_asset_ids)
    except GenerationError as exc:
        raise _fail(exc) from exc
    shot = Shot(
        storyboard_id=sb.id,
        title=body.title,
        description=body.description,
        motion=body.motion,
        duration_seconds=body.duration_seconds,
        reference_asset_ids=refs,
        end_on_next=body.end_on_next,
    )
    shots = list(sb.shots)
    shots.insert(min(body.position, len(shots)) if body.position is not None else len(shots), shot)
    sb.shots = shots
    _renumber(shots)
    _touch(sb)
    await session.commit()
    return await _render(session, await _load(session, access, sb.id), storage, settings)


@router.patch("/{storyboard_id}/shots/{shot_id}", response_model=StoryboardOut)
async def update_shot(
    storyboard_id: uuid.UUID,
    shot_id: uuid.UUID,
    body: ShotUpdate,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    access.require(Action.generate)
    sb = await _load(session, access, storyboard_id)
    shot = _shot(sb, shot_id)
    changes = body.model_dump(exclude_unset=True)
    if "reference_asset_ids" in changes:
        try:
            shot.reference_asset_ids = await svc.check_references(
                session, access.workspace.id, body.reference_asset_ids or []
            )
        except GenerationError as exc:
            raise _fail(exc) from exc
    for key in ("title", "motion", "duration_seconds"):
        if key in changes:
            setattr(shot, key, changes[key])
    if changes.get("description") is not None:
        shot.description = changes["description"]
    if changes.get("end_on_next") is not None:
        shot.end_on_next = changes["end_on_next"]
    _touch(sb)
    await session.commit()
    return await _render(session, await _load(session, access, sb.id), storage, settings)


@router.delete("/{storyboard_id}/shots/{shot_id}", response_model=StoryboardOut)
async def delete_shot(
    storyboard_id: uuid.UUID,
    shot_id: uuid.UUID,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    access.require(Action.generate)
    sb = await _load(session, access, storyboard_id)
    shot = _shot(sb, shot_id)
    shots = [s for s in sb.shots if s.id != shot.id]
    sb.shots = shots
    _renumber(shots)
    _touch(sb)
    await session.commit()
    return await _render(session, await _load(session, access, sb.id), storage, settings)


@router.put("/{storyboard_id}/order", response_model=StoryboardOut)
async def reorder_shots(
    storyboard_id: uuid.UUID,
    body: ShotOrder,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    access.require(Action.generate)
    sb = await _load(session, access, storyboard_id)
    by_id = {s.id: s for s in sb.shots}
    if set(body.shot_ids) != set(by_id) or len(body.shot_ids) != len(by_id):
        raise HTTPException(422, "Send every shot id exactly once")
    shots = [by_id[i] for i in body.shot_ids]
    _renumber(shots)
    sb.shots = shots
    _touch(sb)
    await session.commit()
    return await _render(session, await _load(session, access, sb.id), storage, settings)


@router.put("/{storyboard_id}/shots/{shot_id}/keyframe", response_model=StoryboardOut)
async def pick_keyframe(
    storyboard_id: uuid.UUID,
    shot_id: uuid.UUID,
    body: KeyframePick,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    """Use an existing image (an upload or any gallery image) as the shot's keyframe."""
    access.require(Action.generate)
    sb = await _load(session, access, storyboard_id)
    shot = _shot(sb, shot_id)
    asset = await session.get(Asset, body.asset_id)
    if asset is None or asset.workspace_id != access.workspace.id:
        raise HTTPException(404, "Image not found")
    if asset.media_type != MediaType.image:
        raise HTTPException(422, "A keyframe must be an image")
    shot.keyframe_asset_id = asset.id
    shot.keyframe_job_id = None
    _touch(sb)
    await session.commit()
    return await _render(session, await _load(session, access, sb.id), storage, settings)


# --------------------------------------------------------------------------- generation


def _active(job_id: uuid.UUID | None, jobs: dict[uuid.UUID, Job]) -> bool:
    job = jobs.get(job_id) if job_id else None
    return job is not None and job.status in (JobStatus.queued, JobStatus.running)


@router.post("/{storyboard_id}/generate", response_model=StoryboardOut)
async def generate(
    storyboard_id: uuid.UUID,
    body: GenerateRequest,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    """Make keyframes or clips for some or all shots, as one all-or-nothing batch:
    if credits or limits don't cover every job, nothing is started."""
    access.require(Action.generate)
    sb = await _load(session, access, storyboard_id)
    jobs = await svc.sync(session, sb)
    shots = sb.shots
    if body.shot_ids is not None:
        missing = set(body.shot_ids) - {s.id for s in shots}
        if missing:
            raise HTTPException(404, "Shot not found")
    explicit = body.shot_ids is not None
    chosen = [s for s in shots if not explicit or s.id in set(body.shot_ids)]
    refs_alive = await svc.live_assets(
        session,
        sb.workspace_id,
        {uuid.UUID(r) for s in chosen for r in s.reference_asset_ids or []},
    )

    plans: list[tuple[Shot, svc.JobPlan]] = []
    for s in chosen:
        idx = shots.index(s)
        label = f"Shot {idx + 1}"
        if body.stage == "keyframes":
            if _active(s.keyframe_job_id, jobs):
                continue
            if s.keyframe_asset_id and not body.redo:
                continue
            refs = [r for r in s.reference_asset_ids or [] if uuid.UUID(r) in refs_alive]
            make = lambda s=s, refs=refs: svc.keyframe_plan(settings, sb, s, refs)  # noqa: E731
        else:
            if _active(s.clip_job_id, jobs):
                continue
            stale = s.clip_asset_id and s.clip_keyframe_id != s.keyframe_asset_id
            if s.clip_asset_id and not stale and not body.redo:
                continue
            if s.keyframe_asset_id is None:
                if _active(s.keyframe_job_id, jobs):
                    raise HTTPException(409, f"{label}: wait for its keyframe to finish")
                raise HTTPException(422, f"{label}: make a keyframe first")
            nxt = shots[idx + 1] if idx + 1 < len(shots) else None
            make = lambda s=s, nxt=nxt: svc.clip_plan(settings, sb, s, nxt)  # noqa: E731
        if not (s.description.strip() or s.title or (body.stage == "clips" and s.motion)):
            raise HTTPException(422, f"{label}: describe the shot first")
        try:
            plans.append((s, make()))
        except GenerationError as exc:
            raise HTTPException(exc.status_code, f"{label}: {exc}") from exc

    if not plans:
        await session.commit()
        return await _render(session, sb, storage, settings)
    try:
        await generation.ensure_capacity(session, access, len(plans))
        for s, plan in plans:
            job = await generation.submit_job(
                session,
                access,
                settings,
                model=plan.model,
                operation=plan.operation,
                prompt=plan.prompt,
                params=plan.params,
                inputs=plan.inputs,
                check_active=False,
            )
            job.storyboard_id = sb.id
            if body.stage == "keyframes":
                s.keyframe_job_id = job.id
            else:
                s.clip_job_id = job.id
    except GenerationError as exc:
        await session.rollback()
        if exc.status_code == 402 and len(plans) > 1:
            raise HTTPException(
                402, f"{exc} (This batch starts {len(plans)} generations at once.)"
            ) from exc
        raise _fail(exc) from exc
    _touch(sb)
    await session.commit()
    return await _render(session, await _load(session, access, sb.id), storage, settings)


@router.post("/{storyboard_id}/assemble", response_model=StoryboardOut)
async def assemble(
    storyboard_id: uuid.UUID,
    access: WorkspaceAccess = Depends(workspace_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    """Join every shot's clip, in order, into one video (free)."""
    access.require(Action.generate)
    sb = await _load(session, access, storyboard_id)
    jobs = await svc.sync(session, sb)
    if _active(sb.film_job_id, jobs):
        raise HTTPException(409, "The film is already being assembled")
    if not sb.shots:
        raise HTTPException(422, "Add shots first")
    clips = await svc.live_assets(
        session, sb.workspace_id, {s.clip_asset_id for s in sb.shots if s.clip_asset_id}
    )
    for i, s in enumerate(sb.shots):
        if s.clip_asset_id not in clips:
            busy = _active(s.clip_job_id, jobs)
            raise HTTPException(
                409 if busy else 422,
                f"Shot {i + 1}: {'its clip is still rendering' if busy else 'animate it first'}",
            )
    params = {"transition": sb.transition}
    try:
        job = await generation.submit_job(
            session,
            access,
            settings,
            model=svc.STITCH_MODEL,
            operation="assemble",
            prompt=f"{sb.title} ({len(sb.shots)} shots)",
            params=params,
            inputs=[{"asset_id": str(s.clip_asset_id), "role": "clip"} for s in sb.shots],
            internal=True,
        )
    except GenerationError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    job.storyboard_id = sb.id
    sb.film_job_id = job.id
    _touch(sb)
    await session.commit()
    return await _render(session, await _load(session, access, sb.id), storage, settings)
