"""Debug models for local development and tests (ENABLE_DEBUG_OPERATIONS=true only).

They exercise the whole pipeline without calling a paid provider: `debug/pixel`
returns placeholder images instantly, `debug/clip` simulates a slow video job.
"""

import asyncio
import hashlib
import shutil
import struct
import tempfile
import zlib
from pathlib import Path

from app.models import MediaType
from app.providers import GeneratedMedia, ProviderError

# Smallest valid PNG (1x1 transparent pixel). Used by tests.
PIXEL = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def _png(width: int, height: int, seed: bytes) -> bytes:
    """A smooth two-colour gradient PNG, colours derived from the seed."""
    a = seed[0:3]
    b = seed[3:6]
    rows = []
    for y in range(height):
        row = bytearray(b"\x00")
        for x in range(width):
            t = (x + y) / (width + height)
            row += bytes(int(a[i] * (1 - t) + b[i] * t) for i in range(3))
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 6))
        + chunk(b"IEND", b"")
    )


async def run(ctx) -> list[GeneratedMedia]:
    if ctx.params.get("fail"):
        raise ProviderError("Debug failure requested")
    await ctx.report_progress(0.5)
    n = ctx.params.get("n", 1)
    if ctx.params.get("placeholder", False):
        outputs = []
        for i in range(n):
            seed = hashlib.sha256(f"{ctx.job.prompt}-{i}".encode()).digest()
            outputs.append(
                GeneratedMedia(_png(512, 512, seed), "image/png", MediaType.image, 512, 512)
            )
        return outputs
    return [GeneratedMedia(PIXEL, "image/png", MediaType.image, 1, 1) for _ in range(n)]


async def run_clip(ctx) -> list[GeneratedMedia]:
    """Simulated video: waits a few seconds reporting progress, then renders a test clip."""
    seconds = int(ctx.params.get("duration_seconds", 4))
    for step in range(1, 6):
        await asyncio.sleep(1)
        await ctx.report_progress(step / 6)
        if await ctx.is_canceled():
            return []
    if not shutil.which("ffmpeg"):
        raise ProviderError("The debug video model needs ffmpeg installed")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "clip.mp4"
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=1280x720:rate=24:duration={seconds}",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out),
        )
        await proc.wait()
        if proc.returncode != 0 or not out.exists():
            raise ProviderError("ffmpeg failed to render the debug clip")
        data = out.read_bytes()
    return [GeneratedMedia(data, "video/mp4", MediaType.video, 1280, 720, float(seconds))]
