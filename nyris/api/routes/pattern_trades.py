"""Endpoints de relecture des trades PATTERN (lecture seule, table pattern_trades)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from nyris.api.deps import get_db
from nyris.schemas.pattern_trade import PatternTradeFilters, PatternTradePage, PatternTradeStats
from nyris.strategy.pattern_trades_read import list_pattern_trades, pattern_trades_stats

router = APIRouter(prefix="/pattern", tags=["pattern"])


@router.get("/trades", response_model=PatternTradePage)
def get_pattern_trades(
    filters: Annotated[PatternTradeFilters, Query()],
    db: Session = Depends(get_db),
):
    items, total = list_pattern_trades(db, filters)
    return {"items": items, "total": total, "limit": filters.limit, "offset": filters.offset}


@router.get("/trades/stats", response_model=PatternTradeStats)
def get_pattern_trades_stats(
    filters: Annotated[PatternTradeFilters, Query()],
    db: Session = Depends(get_db),
):
    return pattern_trades_stats(db, filters)
