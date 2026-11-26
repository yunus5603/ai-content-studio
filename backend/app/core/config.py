from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (or a local .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["local", "test", "staging", "production"] = "local"
    database_url: str = "postgresql+asyncpg://postgres@127.0.0.1:5432/studio"

    # "firebase" verifies Google Identity Platform ID tokens. "dev" trusts an
    # X-Dev-User header and must never be enabled in production.
    auth_mode: Literal["firebase", "dev"] = "dev"
    gcp_project_id: str | None = None

    # "gcs" stores media in Cloud Storage; "local" writes to disk (dev and tests).
    storage_backend: Literal["gcs", "local"] = "local"
    gcs_bucket: str | None = None
    local_storage_dir: str = "./.media"
    # Secret used to sign local file URLs. Not used with GCS.
    local_url_secret: str = "dev-only-change-me"
    public_api_url: str = "http://localhost:8000"
    signed_url_ttl_seconds: int = 3600

    max_upload_bytes: int = 500 * 1024 * 1024
    allowed_upload_types: list[str] = [
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "video/mp4",
        "video/quicktime",
        "video/webm",
    ]

    cors_origins: list[str] = ["http://localhost:3000"]

    # Worker
    worker_poll_interval_seconds: float = 1.0
    worker_concurrency: int = 4
    job_timeout_seconds: int = 30 * 60
    job_max_attempts: int = 3
    enable_debug_operations: bool = False

    # Providers
    openai_api_key: str | None = None
    # Vertex AI region. "global" serves the Gemini models; Veo may need e.g. us-central1.
    vertex_location: str = "global"
    vertex_video_location: str = "us-central1"
    # Model used to rewrite prompts ("Enhance prompt").
    prompt_enhancer_model: str = "gemini-3.5-flash-lite"

    # Free credits granted to each new personal workspace (used from step 3).
    signup_free_credits: int = 100

    def validate_for_production(self) -> None:
        if self.env == "production":
            if self.auth_mode != "firebase":
                raise RuntimeError("AUTH_MODE must be 'firebase' in production")
            if self.storage_backend != "gcs" or not self.gcs_bucket:
                raise RuntimeError("STORAGE_BACKEND=gcs and GCS_BUCKET are required in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
