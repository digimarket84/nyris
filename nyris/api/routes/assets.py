"""Endpoints des actifs suivis."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from nyris.api.deps import get_db
from nyris.models.asset import Asset, AssetStatus
from nyris.schemas.asset import AssetRead

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=list[AssetRead])
def list_assets(
    tradeable_only: bool = Query(default=False, description="Ne renvoyer que les actifs tradables"),
    status: AssetStatus | None = Query(default=None, description="Filtrer par statut"),
    db: Session = Depends(get_db),
) -> list[Asset]:
    stmt = select(Asset).order_by(Asset.symbol)
    if tradeable_only:
        stmt = stmt.where(Asset.is_tradeable.is_(True))
    if status is not None:
        stmt = stmt.where(Asset.status == status)
    return list(db.scalars(stmt).all())
