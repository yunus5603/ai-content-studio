"""Worker service entrypoint.

Runs the job loop plus a tiny HTTP server for Cloud Run health checks:
    uvicorn app.worker.main:app --port 8080
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.services.storage import get_storage
from app.worker.runner import work_forever

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.validate_for_production()
    stop = asyncio.Event()
    task = asyncio.create_task(work_forever(SessionLocal, get_storage(), settings, stop))
    yield
    stop.set()
    await task


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/healthz")
async def healthz():
    return {"ok": True}
