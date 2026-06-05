"""Point d'entrée de l'application FastAPI Nyris."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from nyris.api.routes import (
    assets,
    health,
    market,
    pattern_trades,
    portfolio,
    short_trades,
    strategy,
    trades,
)
from nyris.core.config import settings
from nyris.core.logging import configure_logging

configure_logging()

app = FastAPI(title=settings.app_name, version="0.1.0")

API_V1 = "/api/v1"
app.include_router(health.router)
app.include_router(assets.router, prefix=API_V1)
app.include_router(trades.router, prefix=API_V1)
app.include_router(portfolio.router, prefix=API_V1)
app.include_router(market.router, prefix=API_V1)
app.include_router(strategy.router, prefix=API_V1)
app.include_router(short_trades.router, prefix=API_V1)
app.include_router(pattern_trades.router, prefix=API_V1)

# Dashboard statique (servi en same-origin, accès via tunnel SSH)
app.mount("/ui", StaticFiles(directory="frontend", html=True), name="ui")


@app.get("/", tags=["root"])
def root() -> dict:
    return {"app": settings.app_name, "version": "0.1.0", "docs": "/docs", "ui": "/ui/"}
