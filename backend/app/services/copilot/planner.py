"""Copilot planner: goal -> validated, costed plan.

Two planners produce a Draft: an LLM planner (Gemini on Vertex AI, given the model
catalog) and a rules planner that needs no API. Either way, `finalize` checks every
step against the catalog, repairs what it can, prices each step and fits the budget,
so a plan the user sees can always be submitted.
"""

import json
import logging
import re
import uuid
from typing import Any

from app.catalog import CatalogError, get_model, load_catalog, validate_params
from app.catalog.pricing import estimate_cost, with_fee
from app.catalog.schema import ModelSpec
from app.core.config import Settings
from app.services.copilot.schema import Draft, PlanStep, Preference, StepInput

log = logging.getLogger(__name__)

MAX_STEPS = 8
QUALITY_LEVELS = {"quality": "high", "balanced": None, "budget": "low"}
VIDEO_WORDS = re.compile(
    r"\b(video|videos|clip|clips|animate|animated|animation|motion|moving|trailer|teaser|"
    r"reel|reels|commercial|footage|film|movie|cinematic shot|b-roll|tiktok|short)\b",
    re.I,
)
EDIT_WORDS = re.compile(
    r"\b(edit|change|replace|remove|add|swap|turn|make (it|this|them)|restyle|style|"
    r"background|retouch|fix|recolou?r|put)\b",
    re.I,
)
COUNT = re.compile(
    r"\b(\d{1,2}|two|three|four|five|six|eight)\s+(?:[a-z-]+\s+){0,2}(images|pictures|photos|variations|"
    r"options|versions|concepts|ideas|shots|takes)\b",
    re.I,
)
WORD_NUMBERS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8}


class PlanningError(Exception):
    pass


# --- catalog helpers --------------------------------------------------------------


def candidates(operation: str, include_debug: bool = False) -> list[ModelSpec]:
    """Models that can do an operation, excluding deprecated and debug ones."""
    return [
        m
        for m in load_catalog(include_debug).values()
        if m.operation(operation) and m.status != "deprecated" and m.provider != "debug"
    ]


def default_price(spec: ModelSpec, operation: str) -> float:
    try:
        return estimate_cost(spec, validate_params(spec, operation, {}))
    except CatalogError:
        return float("inf")


def choose_model(operation: str, preference: Preference) -> ModelSpec:
    """Pick the model for an operation: best quality, cheapest, or a fast middle ground."""
    pool = candidates(operation)
    if not pool:
        raise PlanningError(f"No model can do {operation.replace('_', ' ')}")
    ga = [m for m in pool if m.status == "ga"] or pool
    by_price = sorted(ga, key=lambda m: default_price(m, operation))
    if preference == "budget":
        return sorted(pool, key=lambda m: default_price(m, operation))[0]
    if preference == "quality":
        best = [m for m in ga if "best-quality" in m.tags]
        return best[0] if best else by_price[-1]
    fast = [m for m in by_price if "fast" in m.tags and "best-quality" not in m.tags]
    return fast[0] if fast else by_price[len(by_price) // 2]


def _orientation(goal: str) -> str | None:
    g = goal.lower()
    if re.search(r"\b(vertical|portrait|9:16|story|stories|reels?|tiktok|phone wallpaper)\b", g):
        return "portrait"
    if re.search(r"\b(square|1:1|instagram post|avatar|profile picture|logo|icon)\b", g):
        return "square"
    if re.search(r"\b(wide|landscape|16:9|youtube|banner|header|cover|desktop|cinematic)\b", g):
        return "landscape"
    return None


def _shape(value: Any) -> str | None:
    """'16:9' / '1536x1024' -> landscape | portrait | square."""
    m = re.fullmatch(r"(\d+)\s*[:x]\s*(\d+)", str(value))
    if not m:
        return None
    w, h = int(m[1]), int(m[2])
    return "square" if w == h else ("landscape" if w > h else "portrait")


def tune_params(
    spec: ModelSpec, operation: str, preference: Preference, goal: str = "", count: int = 1
) -> dict[str, Any]:
    """Settings for a preference: quality, resolution, length, audio, aspect, image count."""
    wanted: dict[str, Any] = {}
    orientation = _orientation(goal)
    for p in spec.params_for(operation):
        values = [o.value for o in p.options]
        if p.name == "quality" and values:
            level = QUALITY_LEVELS[preference]
            if level in values:
                wanted[p.name] = level
        elif p.name == "resolution" and values:
            ranked = sorted(values, key=lambda v: int(re.sub(r"\D", "", str(v)) or 0))
            if preference == "quality":
                wanted[p.name] = ranked[-1]
            elif preference == "budget":
                wanted[p.name] = ranked[0]
        elif p.name == "generate_audio" and preference == "budget":
            wanted[p.name] = False
        elif p.name == "duration_seconds" and values:
            asked = re.search(r"\b(\d{1,2})\s*-?\s*(s|sec|secs|seconds?)\b", goal, re.I)
            if asked:
                wanted[p.name] = min(values, key=lambda v: abs(float(v) - int(asked[1])))
            elif preference == "budget":
                wanted[p.name] = min(values)
        elif p.name in ("aspect_ratio", "size") and orientation:
            # Prefer the default if it already has the right shape, else the first match.
            if _shape(p.default) == orientation:
                continue
            match = next((v for v in values if _shape(v) == orientation), None)
            if match is not None:
                wanted[p.name] = match
        elif p.name in ("n", "number_of_videos") and count > 1 and spec.media_type == "image":
            wanted[p.name] = int(min(count, p.max or count))
    return safe_params(spec, operation, wanted)


def safe_params(spec: ModelSpec, operation: str, params: dict[str, Any]) -> dict[str, Any]:
    """Keep each requested setting only if it is valid together with the ones kept so far."""
    try:
        return validate_params(spec, operation, params)
    except CatalogError:
        pass
    kept: dict[str, Any] = {}
    for key, value in params.items():
        try:
            validate_params(spec, operation, {**kept, key: value})
            kept[key] = value
        except CatalogError:
            continue
    return validate_params(spec, operation, kept)


def step_price(spec: ModelSpec, params: dict[str, Any]) -> float:
    return with_fee(estimate_cost(spec, params))


# --- rules planner ----------------------------------------------------------------


def _count(goal: str) -> int:
    m = COUNT.search(goal)
    if not m:
        return 1
    raw = m[1].lower()
    return max(1, min(int(WORD_NUMBERS.get(raw, raw)), 8))


def _title(goal: str) -> str:
    words = re.sub(r"\s+", " ", goal).strip().rstrip(".!")
    return (words[:60] + "…") if len(words) > 60 else words


def rules_plan(goal: str, preference: Preference, attachments: dict[uuid.UUID, str]) -> Draft:
    images = [a for a, kind in attachments.items() if kind == "image"]
    wants_video = bool(VIDEO_WORDS.search(goal))
    count = _count(goal)
    steps: list[PlanStep] = []
    notes: list[str] = []

    def add(title: str, operation: str, prompt: str, why: str, inputs=None, n: int = 1):
        spec = choose_model(operation, preference)
        steps.append(
            PlanStep(
                id=f"s{len(steps) + 1}",
                title=title,
                model=spec.id,
                operation=operation,
                prompt=prompt,
                params=tune_params(spec, operation, preference, goal, n),
                inputs=inputs or [],
                why=why,
            )
        )
        return steps[-1]

    if images and wants_video:
        add(
            "Animate your image",
            "image_to_video",
            goal,
            "You attached an image, so it becomes the first frame and the video moves from there.",
            [StepInput(role="first_frame", asset_id=images[0])],
        )
    elif images:
        add(
            "Edit your image",
            "image_edit",
            goal,
            "You attached an image, so it is edited rather than starting from scratch.",
            [StepInput(role="image", asset_id=a) for a in images[:4]],
            n=count,
        )
    elif wants_video and preference == "budget":
        add(
            "Generate the video",
            "text_to_video",
            goal,
            "Straight to video with the lowest-cost model, which keeps the price down.",
        )
    elif wants_video:
        key = add(
            "Design the opening frame",
            "text_to_image",
            f"Opening frame, a single still: {goal}",
            "A still costs cents, so the look is fixed before paying for video, "
            "and it keeps the scene consistent.",
        )
        add(
            "Bring it to life",
            "image_to_video",
            goal,
            "Animates the opening frame into the final clip.",
            [StepInput(role="first_frame", from_step=key.id)],
        )
        notes.append("Want different opening frames to choose from? Ask for options first.")
    else:
        add(
            "Generate the images" if count > 1 else "Generate the image",
            "text_to_image",
            goal,
            "Picked for your quality preference.",
            n=count,
        )
    summary = {
        "quality": "Uses the highest quality models and settings.",
        "balanced": "Balances quality, speed and price.",
        "budget": "Keeps the price as low as possible.",
    }[preference]
    return Draft(title=_title(goal), summary=summary, steps=steps, notes=notes, planner="rules")


# --- LLM planner ------------------------------------------------------------------


def catalog_brief(include_debug: bool = False) -> str:
    lines = []
    for m in load_catalog(include_debug).values():
        if m.status == "deprecated" or (m.provider == "debug" and not include_debug):
            continue
        ops = []
        for op in m.operations:
            ins = ", ".join(f"{i.role} {i.min}-{i.max}" for i in op.inputs)
            ops.append(f"{op.operation}({ins})" if ins else op.operation)
        params = []
        for p in m.params:
            if p.advanced or p.type == "text":
                continue
            if p.options:
                vals = "|".join(str(o.value) for o in p.options[:10])
                params.append(f"{p.name}=[{vals}] default {p.default}")
            elif p.type in ("int", "float"):
                lo = "" if p.min is None else f"{p.min:g}"
                hi = "" if p.max is None else f"{p.max:g}"
                params.append(f"{p.name}={p.type} {lo}-{hi} default {p.default}")
            elif p.type == "bool":
                params.append(f"{p.name}=bool default {p.default}")
        first = m.operations[0].operation
        price = step_price(m, validate_params(m, first, {}))
        unit = "image" if m.pricing.unit == "image" else "clip at defaults"
        lines.append(
            f"- {m.id} | {m.name} | {m.media_type} | {m.status} | tags: {', '.join(m.tags)}\n"
            f"  {m.description}\n  ops: {'; '.join(ops)}\n  params: {'; '.join(params)}\n"
            f"  price: about ${price:.3f} per {unit} at default settings"
        )
    return "\n".join(lines)


_SYSTEM = """You are the copilot of an AI image and video studio. Turn the user's goal
into the best plan of generation steps using ONLY the models below.

Models:
{catalog}

Rules:
- Use as few steps as the goal needs (max {max_steps}). Each step is one generation.
- A step may use an earlier step's output as an input with from_step (and output_index
  when that step makes several outputs), or an attached file with asset_id.
- For videos, a strong pattern is: design a key frame with an image model, then
  image_to_video with that frame as first_frame. Skip it on a tight budget.
- Use only operations, params and values listed for the chosen model. Omit params
  to use defaults.
- Write each step's prompt in full, vivid and specific (subject, setting, composition,
  lighting, style, mood; for video also camera movement, action and sound). Keep the
  user's intent and any quoted text exactly.
- Preference "{preference}": quality = best models and settings; balanced = good
  quality at reasonable speed and price; budget = cheapest that still does the job.
{budget}
Attached files: {attachments}

Reply with JSON only:
{{"title": "3-6 words", "summary": "one or two sentences on the approach",
 "notes": ["optional tips"],
 "steps": [{{"id": "s1", "title": "short", "model": "<model id>",
   "operation": "<operation>", "prompt": "...", "params": {{}},
   "inputs": [{{"role": "first_frame", "from_step": "s0", "output_index": 0}}],
   "why": "one sentence"}}]}}"""


async def llm_plan(
    goal: str,
    preference: Preference,
    budget_usd: float | None,
    attachments: dict[uuid.UUID, str],
    settings: Settings,
    previous: Draft | None = None,
    instruction: str | None = None,
) -> Draft:
    from google.genai import types

    from app.providers.clients import vertex_client

    system = _SYSTEM.format(
        catalog=catalog_brief(),
        max_steps=MAX_STEPS,
        preference=preference,
        budget=f"- Total budget: ${budget_usd:.2f} including fees.\n" if budget_usd else "",
        attachments=", ".join(f"{a} ({k})" for a, k in attachments.items()) or "none",
    )
    contents = f"Goal: {goal}"
    if previous is not None:
        contents += "\n\nCurrent plan:\n" + previous.model_dump_json(
            include={"title", "summary", "steps"}
        )
    if instruction:
        contents += f"\n\nChange requested: {instruction}"
    resp = await vertex_client().aio.models.generate_content(
        model=settings.copilot_model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.4,
            max_output_tokens=4000,
            response_mime_type="application/json",
        ),
    )
    data = json.loads(resp.text or "{}")
    steps = []
    for i, raw in enumerate(data.get("steps") or []):
        raw.setdefault("id", f"s{i + 1}")
        raw.setdefault("title", f"Step {i + 1}")
        raw["inputs"] = [x for x in raw.get("inputs") or [] if isinstance(x, dict)]
        for x in raw["inputs"]:
            if x.get("asset_id") in ("", None):
                x.pop("asset_id", None)
        steps.append(PlanStep.model_validate(raw))
    if not steps:
        raise PlanningError("The planner returned no steps")
    return Draft(
        title=str(data.get("title") or "")[:200],
        summary=str(data.get("summary") or ""),
        notes=[str(n) for n in data.get("notes") or []][:5],
        steps=steps,
        planner="llm",
    )


def use_llm(settings: Settings) -> bool:
    if settings.copilot_planner == "llm":
        return True
    return settings.copilot_planner == "auto" and bool(settings.gcp_project_id)


async def make_plan(
    goal: str,
    preference: Preference,
    budget_usd: float | None,
    attachments: dict[uuid.UUID, str],
    settings: Settings,
    previous: Draft | None = None,
    instruction: str | None = None,
) -> Draft:
    """Plan with the LLM when available, falling back to the rules planner."""
    draft = None
    if use_llm(settings):
        try:
            draft = await llm_plan(
                goal, preference, budget_usd, attachments, settings, previous, instruction
            )
        except Exception:
            log.exception("LLM planner failed; using rules")
    if draft is None:
        text = f"{goal}. {instruction}" if instruction else goal
        draft = rules_plan(text, preference, attachments)
    return finalize(draft, preference, budget_usd, attachments)


# --- validation -------------------------------------------------------------------


def _fallback_operation(operation: str) -> str:
    return {"image_to_video": "text_to_video", "image_edit": "text_to_image"}.get(
        operation, "text_to_image" if operation == "inpaint" else operation
    )


def finalize(
    draft: Draft,
    preference: Preference,
    budget_usd: float | None,
    attachments: dict[uuid.UUID, str],
    include_debug: bool = False,
) -> Draft:
    """Make every step valid against the catalog, price it, and fit the budget."""
    notes = list(draft.notes)
    steps: list[PlanStep] = []
    renamed: dict[str, str] = {}
    produced: dict[str, str] = {}  # step id -> media type of its outputs

    for raw in draft.steps[:MAX_STEPS]:
        step = raw.model_copy(deep=True)
        new_id = f"s{len(steps) + 1}"
        renamed[step.id] = new_id
        step.id = new_id
        step.status, step.job_id, step.error = "pending", None, None
        step.prompt = (step.prompt or draft.title or "Untitled").strip()[:32000]

        spec = _resolve_model(step, preference, include_debug, notes)
        # Inputs: keep the ones that point at something real and fit the role.
        allowed = {i.role: i for i in (spec.operation(step.operation).inputs)}
        inputs: list[StepInput] = []
        for item in step.inputs:
            rule = allowed.get(item.role)
            if rule is None:
                continue
            if item.from_step:
                src = renamed.get(item.from_step)
                if src and produced.get(src) == rule.media_type:
                    inputs.append(item.model_copy(update={"from_step": src, "asset_id": None}))
            elif item.asset_id and attachments.get(item.asset_id) == rule.media_type:
                inputs.append(item)
        # Fill a required input from the previous image step, or an attached image.
        for role, rule in allowed.items():
            have = sum(1 for i in inputs if i.role == role)
            if have >= rule.min or rule.media_type != "image":
                continue
            prev = next((s.id for s in reversed(steps) if produced.get(s.id) == "image"), None)
            attached = next((a for a, k in attachments.items() if k == "image"), None)
            if prev:
                inputs.append(StepInput(role=role, from_step=prev))
            elif attached:
                inputs.append(StepInput(role=role, asset_id=attached))
        missing = [r for r, rule in allowed.items() if sum(i.role == r for i in inputs) < rule.min]
        if missing:
            fallback = _fallback_operation(step.operation)
            if fallback == step.operation:
                notes.append(f"Dropped “{step.title}”: it needs a file that isn't available.")
                renamed.pop(raw.id, None)
                continue
            step.operation = fallback
            inputs = []
            if spec.operation(fallback) is None:
                spec = choose_model(fallback, preference)
                step.model = spec.id
        step.inputs = inputs
        step.params = safe_params(spec, step.operation, step.params or {})
        step.estimated_price_usd = step_price(spec, step.params)
        steps.append(step)
        produced[step.id] = spec.media_type

    if not steps:
        raise PlanningError("Couldn't make a plan for that. Try describing the result you want.")

    plan = draft.model_copy(update={"steps": steps, "notes": notes})
    total = sum(s.estimated_price_usd for s in steps)
    if budget_usd and total > budget_usd and preference != "budget":
        cheaper = _cheapen(plan, attachments, include_debug)
        cheaper_total = sum(s.estimated_price_usd for s in cheaper.steps)
        if cheaper_total < total:
            plan = cheaper
            plan.notes.append(
                f"Switched to lower-cost models and settings to fit your ${budget_usd:.2f} budget."
            )
            total = cheaper_total
    if budget_usd and total > budget_usd:
        plan.notes.append(
            f"This plan costs about ${total:.2f}, over your ${budget_usd:.2f} budget. "
            "Remove a step or lower the settings."
        )
    return plan


def _resolve_model(
    step: PlanStep, preference: Preference, include_debug: bool, notes: list[str]
) -> ModelSpec:
    try:
        spec = get_model(step.model, include_debug=include_debug)
    except CatalogError:
        spec = None
    if spec is not None and spec.operation(step.operation) is None:
        spec = None
    if spec is None:
        try:
            spec = choose_model(step.operation, preference)
        except PlanningError:
            step.operation = "text_to_image"
            spec = choose_model(step.operation, preference)
        if step.model:
            notes.append(f"“{step.title}” uses {spec.name} instead of {step.model}.")
        step.model = spec.id
    return spec


def _cheapen(plan: Draft, attachments: dict[uuid.UUID, str], include_debug: bool) -> Draft:
    steps = []
    for s in plan.steps:
        spec = choose_model(s.operation, "budget")
        carry = {k: s.params[k] for k in ("aspect_ratio", "size", "n") if k in s.params}
        params = safe_params(
            spec, s.operation, {**tune_params(spec, s.operation, "budget"), **carry}
        )
        steps.append(
            s.model_copy(
                update={
                    "model": spec.id,
                    "params": params,
                    "estimated_price_usd": step_price(spec, params),
                }
            )
        )
    return plan.model_copy(update={"steps": steps, "notes": list(plan.notes)})
