"""Endpoint d'agrégation du portefeuille simulé (filtrable)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from nyris.api.deps import get_db
from nyris.schemas.portfolio import PortfolioFilters, PortfolioSummary
from nyris.services import portfolio as portfolio_service

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/summary", response_model=PortfolioSummary)
def portfolio_summary(
    filters: Annotated[PortfolioFilters, Query()],
    db: Session = Depends(get_db),
):
    return portfolio_service.build_summary(
        db, from_=filters.from_, to=filters.to, asset_id=filters.asset_id
    )
