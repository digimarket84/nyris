"""Endpoints de relecture de la stratégie (lecture seule)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from nyris.api.deps import get_db
from nyris.schemas.strategy_decision import StrategyDecisionFilters, StrategyDecisionPage
from nyris.strategy.decisions_read import list_decisions

router = APIRouter(prefix="/strategy", tags=["strategy"])


@router.get("/decisions", response_model=StrategyDecisionPage)
def get_decisions(
    filters: Annotated[StrategyDecisionFilters, Query()],
    db: Session = Depends(get_db),
):
    items, total = list_decisions(db, filters)
    return {"items": items, "total": total, "limit": filters.limit, "offset": filters.offset}
