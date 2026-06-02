"""Endpoints données de marché (Binance read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from nyris.api.deps import get_db
from nyris.core.exceptions import ConflictError, NotFoundError
from nyris.schemas.market import MarketPrice, MarketPrices, MarketSyncResult
from nyris.services import market as market_service
from nyris.services.binance import (
    BinanceBadResponse,
    BinanceSymbolNotFound,
    BinanceUnavailable,
)

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/price", response_model=MarketPrice)
def market_price(asset_id: int = Query(..., gt=0), db: Session = Depends(get_db)):
    try:
        return market_service.get_price_for_asset(db, asset_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ConflictError, BinanceSymbolNotFound) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BinanceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BinanceBadResponse as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/prices", response_model=MarketPrices)
def market_prices(db: Session = Depends(get_db)):
    try:
        return market_service.get_all_prices(db)
    except BinanceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BinanceBadResponse as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/sync", response_model=MarketSyncResult)
def market_sync(db: Session = Depends(get_db)):
    try:
        return market_service.sync_symbols(db)
    except BinanceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BinanceBadResponse as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
