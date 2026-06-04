"""Endpoints de relecture des trades SHORT (lecture seule, table short_trades)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from nyris.api.deps import get_db
from nyris.schemas.short_trade import ShortTradeFilters, ShortTradePage, ShortTradeStats
from nyris.strategy.short_trades_read import list_short_trades, short_trades_stats

router = APIRouter(prefix="/short", tags=["short"])


@router.get("/trades", response_model=ShortTradePage)
def get_short_trades(
    filters: Annotated[ShortTradeFilters, Query()],
    db: Session = Depends(get_db),
):
    items, total = list_short_trades(db, filters)
    return {"items": items, "total": total, "limit": filters.limit, "offset": filters.offset}


@router.get("/trades/stats", response_model=ShortTradeStats)
def get_short_trades_stats(
    filters: Annotated[ShortTradeFilters, Query()],
    db: Session = Depends(get_db),
):
    return short_trades_stats(db, filters)
