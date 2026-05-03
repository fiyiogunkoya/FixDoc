"""FastAPI application factory."""
import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import (
    analyze,
    auth,
    fixes,
    github_webhooks,
    health,
    integrations,
    pending,
    teams,
    webhooks,
)


def _configure_logging() -> None:
    """Mirror uvicorn's INFO+stdout setup for our `fixdoc.*` loggers so
    integration failures show up in Railway logs without extra config.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    for name in ("fixdoc", "fixdoc.analyze"):
        log = logging.getLogger(name)
        if not log.handlers:
            log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging()

    app = FastAPI(
        title="FixDoc API",
        version="0.0.1",
        docs_url="/docs" if settings.environment != "production" or settings.debug else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(teams.router)
    app.include_router(fixes.router)
    app.include_router(pending.router)
    app.include_router(analyze.router)
    app.include_router(integrations.router)
    app.include_router(webhooks.router)
    app.include_router(github_webhooks.router)

    return app
