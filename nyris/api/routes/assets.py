"""Endpoints des actifs suivis."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from nyris.api.deps import get_db
from nyris.models.asset import Asset
from nyris.schemas.asset import AssetRead

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=list[AssetRead])
def list_assets(
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[Asset]:
    stmt = select(Asset).order_by(Asset.symbol)
    if active_only:
        stmt = stmt.where(Asset.is_active.is_(True))
    return list(db.scalars(stmt).all())
