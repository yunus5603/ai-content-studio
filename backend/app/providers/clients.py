"""Shared, lazily created SDK clients."""

from functools import lru_cache

from app.core.config import get_settings


@lru_cache
def openai_client():
    from openai import AsyncOpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return AsyncOpenAI(api_key=settings.openai_api_key, max_retries=3, timeout=600)


@lru_cache
def vertex_client(location: str | None = None):
    from google import genai

    settings = get_settings()
    if not settings.gcp_project_id:
        raise RuntimeError("GCP_PROJECT_ID is not set")
    return genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=location or settings.vertex_location,
    )
