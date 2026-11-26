"""Identify uploaded media from its first bytes, not the client's claim."""

from collections.abc import Callable

from app.models import MediaType

_SIGNATURES: list[tuple[str, MediaType, Callable[[bytes], bool]]] = [
    ("image/png", MediaType.image, lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    ("image/jpeg", MediaType.image, lambda b: b.startswith(b"\xff\xd8\xff")),
    ("image/gif", MediaType.image, lambda b: b[:6] in (b"GIF87a", b"GIF89a")),
    ("image/webp", MediaType.image, lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP"),
    ("video/webm", MediaType.video, lambda b: b.startswith(b"\x1a\x45\xdf\xa3")),
    ("video/quicktime", MediaType.video, lambda b: b[4:8] == b"ftyp" and b[8:10] == b"qt"),
    ("video/mp4", MediaType.video, lambda b: b[4:8] == b"ftyp"),
]

EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "video/webm": "webm",
    "video/quicktime": "mov",
    "video/mp4": "mp4",
}


def sniff(head: bytes) -> tuple[str, MediaType] | None:
    for content_type, media_type, matches in _SIGNATURES:
        if matches(head):
            return content_type, media_type
    return None
