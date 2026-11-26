"""Prompt enhancement: rewrite a rough idea into a detailed prompt for the chosen model."""

from app.catalog.schema import ModelSpec
from app.core.config import get_settings

_SYSTEM = """You rewrite prompts for AI {media} generation.
Turn the user's idea into one vivid, specific prompt for {model}.
Describe subject, setting, composition, lighting, style and mood.{video_extra}
Keep the user's intent and any text they want shown, in quotes, exactly.
Write in the user's language. Reply with the prompt only, no preamble, under 120 words."""

_VIDEO_EXTRA = (
    " For video, also describe camera movement, the action over time, and"
    " sound (dialogue in quotes, effects, ambience)."
)


async def enhance_prompt(prompt: str, model: ModelSpec | None) -> str:
    from google.genai import types

    from app.providers.clients import vertex_client

    media = model.media_type if model else "image"
    system = _SYSTEM.format(
        media=media,
        model=model.name if model else "a modern image model",
        video_extra=_VIDEO_EXTRA if media == "video" else "",
    )
    resp = await vertex_client().aio.models.generate_content(
        model=get_settings().prompt_enhancer_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system, temperature=0.8, max_output_tokens=400
        ),
    )
    text = (resp.text or "").strip().strip('"')
    return text or prompt
