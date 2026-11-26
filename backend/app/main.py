import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    admin,
    assets,
    billing,
    catalog,
    copilot,
    files,
    jobs,
    me,
    prompts,
    shares,
    storyboards,
    workspaces,
)
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate_for_production()
    app = FastAPI(title="AI Content Studio API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz", tags=["health"])
    async def healthz():
        return {"ok": True}

    for module in (me, workspaces, assets, jobs, catalog, prompts, shares, billing, admin, copilot):
        app.include_router(module.router, prefix="/v1")
    if settings.storage_backend == "local":
        app.include_router(files.router)
    return app


app = create_app()
