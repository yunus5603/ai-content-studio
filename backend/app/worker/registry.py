"""Operations the worker knows how to run.

Step 2 registers real providers here (OpenAI, Vertex AI) driven by the model
catalog. Step 1 ships only the plumbing and a debug operation for tests.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
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


Handler = Callable[["JobContext"], Awaitable[list[GeneratedMedia]]]


@dataclass
class Operation:
    provider: str
    model: str
    operation: str
    handler: Handler
    debug_only: bool = False
    meta: dict = field(default_factory=dict)


_REGISTRY: dict[tuple[str, str, str], Operation] = {}


class UnknownOperation(LookupError):
    pass


def register(op: Operation) -> None:
    _REGISTRY[(op.provider, op.model, op.operation)] = op


def resolve(provider: str, model: str, operation: str, allow_debug: bool) -> Operation:
    op = _REGISTRY.get((provider, model, operation))
    if op is None or (op.debug_only and not allow_debug):
        raise UnknownOperation(f"{provider}/{model} does not support {operation}")
    return op


# ---- Debug operation -----------------------------------------------------

# Smallest valid PNG (1x1 transparent pixel).
_PIXEL = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


async def _debug_pixel(ctx: "JobContext") -> list[GeneratedMedia]:
    if ctx.job.params.get("fail"):
        raise RuntimeError("Debug failure requested")
    await ctx.report_progress(0.5)
    count = int(ctx.job.params.get("n", 1))
    return [GeneratedMedia(_PIXEL, "image/png", MediaType.image, 1, 1) for _ in range(count)]


register(Operation("debug", "pixel", "text_to_image", _debug_pixel, debug_only=True))
