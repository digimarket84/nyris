"""Point d'entrée de l'application FastAPI Nyris."""

from __future__ import annotations

from fastapi import FastAPI

from nyris.api.routes import assets, health, trades
from nyris.core.config import settings
from nyris.core.logging import configure_logging

configure_logging()

app = FastAPI(title=settings.app_name, version="0.1.0")

API_V1 = "/api/v1"
app.include_router(health.router)
app.include_router(assets.router, prefix=API_V1)
app.include_router(trades.router, prefix=API_V1)


@app.get("/", tags=["root"])
def root() -> dict:
    return {"app": settings.app_name, "version": "0.1.0", "docs": "/docs"}
