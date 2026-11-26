"""Provider adapters: turn a validated job into calls to OpenAI or Vertex AI.

Each adapter is an async function taking a JobContext and returning the media
it produced. The catalog (models.yaml) says which adapter serves which model.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models import MediaType

if TYPE_CHECKING:
    from app.worker.runner import JobContext


@dataclass
class GeneratedMedia:
    data: bytes
    content_type: str
    media_type: MediaType
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None


class ProviderError(Exception):
    """A failure we can explain to the user (policy block, bad input, no output)."""


Adapter = Callable[["JobContext"], Awaitable[list[GeneratedMedia]]]


def get_adapter(name: str) -> Adapter:
    # Imported lazily so the API process doesn't load provider SDKs it never uses.
    if name == "openai_image":
        from app.providers.openai_image import run
    elif name == "vertex_gemini_image":
        from app.providers.vertex_gemini_image import run
    elif name == "vertex_veo":
        from app.providers.vertex_veo import run
    elif name == "debug_pixel":
        from app.providers.debug import run
    elif name == "stitch":
        from app.providers.stitch import run
    elif name == "debug_clip":
        from app.providers.debug import run_clip as run
    else:
        raise LookupError(f"No adapter named {name}")
    return run


def size_of(value: object) -> tuple[int | None, int | None]:
    if isinstance(value, str) and "x" in value:
        w, h = value.split("x")
        return int(w), int(h)
    return None, None
