"""Where media files live.

GCS in deployed environments; a local folder for development and tests. Both
hand out time-limited URLs so the browser fetches media directly.
"""

import asyncio
import hashlib
import hmac
import time
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from app.core.config import Settings, get_settings


class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def url(self, key: str) -> str: ...


class LocalStorage:
    def __init__(self, settings: Settings):
        self.root = Path(settings.local_storage_dir).resolve()
        self.secret = settings.local_url_secret.encode()
        self.base_url = settings.public_api_url.rstrip("/")
        self.ttl = settings.signed_url_ttl_seconds

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def sign(self, key: str, expires: int) -> str:
        return hmac.new(self.secret, f"{key}:{expires}".encode(), hashlib.sha256).hexdigest()

    def verify(self, key: str, expires: int, sig: str) -> bool:
        return expires >= time.time() and hmac.compare_digest(self.sign(key, expires), sig)

    def file_path(self, key: str) -> Path:
        return self._path(key)

    async def url(self, key: str) -> str:
        expires = int(time.time()) + self.ttl
        return f"{self.base_url}/files/{quote(key)}?expires={expires}&sig={self.sign(key, expires)}"


class GCSStorage:
    def __init__(self, settings: Settings):
        from google.cloud import storage

        if not settings.gcs_bucket:
            raise RuntimeError("GCS_BUCKET is required when STORAGE_BACKEND=gcs")
        self.client = storage.Client(project=settings.gcp_project_id)
        self.bucket = self.client.bucket(settings.gcs_bucket)
        self.ttl = settings.signed_url_ttl_seconds

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        blob = self.bucket.blob(key)
        await asyncio.to_thread(blob.upload_from_string, data, content_type=content_type)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self.bucket.blob(key).download_as_bytes)

    async def delete(self, key: str) -> None:
        from google.api_core.exceptions import NotFound

        try:
            await asyncio.to_thread(self.bucket.blob(key).delete)
        except NotFound:
            pass

    def _signed_url(self, key: str) -> str:
        import datetime

        import google.auth
        from google.auth.transport import requests as ga_requests

        # On Cloud Run there is no private key file; sign through the IAM API
        # using the service account's access token.
        credentials, _ = google.auth.default()
        credentials.refresh(ga_requests.Request())
        return self.bucket.blob(key).generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(seconds=self.ttl),
            method="GET",
            service_account_email=getattr(credentials, "service_account_email", None),
            access_token=credentials.token,
        )

    async def url(self, key: str) -> str:
        return await asyncio.to_thread(self._signed_url, key)


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_backend == "gcs":
        return GCSStorage(settings)
    return LocalStorage(settings)
