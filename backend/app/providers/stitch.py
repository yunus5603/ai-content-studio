"""Joins storyboard clips into one video with ffmpeg (internal model `studio/stitch`).

Clips can differ in size, frame rate and whether they have audio (Veo can skip
audio), so every clip is normalised to the first clip's frame size, 24 fps and
stereo 48 kHz audio (silence where a clip has none) before joining. Transitions
are hard cuts or crossfades.
"""

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from app.models import MediaType
from app.providers import GeneratedMedia, ProviderError

FPS = 24


async def _run(*args: str) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    return proc.returncode, out, err


async def probe(path: Path) -> tuple[int, int, float, bool]:
    """(width, height, duration_seconds, has_audio) of a video file."""
    code, out, _ = await _run(
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(path),
    )
    if code != 0:
        raise ProviderError("One of the clips isn't a readable video")
    info = json.loads(out)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise ProviderError("One of the clips has no video track")
    duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise ProviderError("One of the clips has no length")
    has_audio = any(s.get("codec_type") == "audio" for s in info["streams"])
    return int(video["width"]), int(video["height"]), duration, has_audio


def build_filter(
    clips: list[tuple[float, bool]], width: int, height: int, transition: str, fade: float
) -> tuple[str, float]:
    """ffmpeg filter graph joining N inputs, and the resulting duration."""
    parts = []
    for i, (duration, has_audio) in enumerate(clips):
        parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS},format=yuv420p,"
            f"trim=duration={duration:.3f},setpts=PTS-STARTPTS[v{i}]"
        )
        audio = (
            f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,apad,"
            if has_audio
            else "anullsrc=r=48000:cl=stereo,"
        )
        parts.append(f"{audio}atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[a{i}]")

    n = len(clips)
    total = sum(d for d, _ in clips)
    if transition != "fade" or n == 1:
        joined = "".join(f"[v{i}][a{i}]" for i in range(n))
        parts.append(f"{joined}concat=n={n}:v=1:a=1[v][a]")
        return ";".join(parts), total

    vprev, aprev, offset = "v0", "a0", 0.0
    for i in range(1, n):
        offset += clips[i - 1][0] - fade
        vout = "v" if i == n - 1 else f"vx{i}"
        aout = "a" if i == n - 1 else f"ax{i}"
        parts.append(
            f"[{vprev}][v{i}]xfade=transition=fade:duration={fade:.3f}:offset={offset:.3f}[{vout}]"
        )
        parts.append(f"[{aprev}][a{i}]acrossfade=d={fade:.3f}[{aout}]")
        vprev, aprev = vout, aout
    return ";".join(parts), total - fade * (n - 1)


async def run(ctx) -> list[GeneratedMedia]:
    clips = ctx.inputs("clip")
    if not clips:
        raise ProviderError("There are no clips to assemble")
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        raise ProviderError("Assembling clips needs ffmpeg on the worker")
    await ctx.report_progress(0.05)
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, (_asset, data) in enumerate(clips):
            path = Path(tmp) / f"in{i}.mp4"
            path.write_bytes(data)
            paths.append(path)
        probes = [await probe(p) for p in paths]
        width, height = probes[0][0] // 2 * 2, probes[0][1] // 2 * 2
        transition = ctx.params.get("transition", "cut")
        # A crossfade can't be longer than half the shortest clip.
        fade = min(float(ctx.params.get("fade_seconds", 0.5)), min(p[2] for p in probes) / 2)
        graph, duration = build_filter(
            [(p[2], p[3]) for p in probes], width, height, transition, fade
        )
        await ctx.report_progress(0.2)
        out = Path(tmp) / "film.mp4"
        args = ["ffmpeg", "-loglevel", "error", "-y"]
        for p in paths:
            args += ["-i", str(p)]
        args += [
            "-filter_complex",
            graph,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(out),
        ]
        code, _, err = await _run(*args)
        if code != 0 or not out.exists():
            raise ProviderError(f"Couldn't assemble the clips: {err.decode()[-300:].strip()}")
        data = out.read_bytes()
    await ctx.report_progress(0.95)
    return [GeneratedMedia(data, "video/mp4", MediaType.video, width, height, round(duration, 3))]
