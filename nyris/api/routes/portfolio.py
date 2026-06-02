"""Endpoint d'agrégation du portefeuille simulé."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from nyris.api.deps import get_db
from nyris.schemas.portfolio import PortfolioSummary
from nyris.services import portfolio as portfolio_service

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/summary", response_model=PortfolioSummary)
def portfolio_summary(db: Session = Depends(get_db)):
    return portfolio_service.build_summary(db)
