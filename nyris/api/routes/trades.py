"""Endpoints des trades simulés."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from nyris.api.deps import get_db
from nyris.core.exceptions import ConflictError, NotFoundError
from nyris.models.simulated_trade import TradeStatus
from nyris.schemas.history import TradeHistoryFilters, TradeHistoryPage
from nyris.schemas.trade import TradeClose, TradeCreate, TradeRead
from nyris.services import trades as trades_service

router = APIRouter(prefix="/trades", tags=["trades"])


@router.post("", response_model=TradeRead, status_code=status.HTTP_201_CREATED)
def create_trade(payload: TradeCreate, db: Session = Depends(get_db)):
    try:
        return trades_service.create_trade(db, payload)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[TradeRead])
def list_trades(
    status_filter: TradeStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return trades_service.list_trades(db, status=status_filter, limit=limit, offset=offset)


# IMPORTANT : déclarer /history AVANT /{trade_id} (sinon "history" matche {trade_id})
@router.get("/history", response_model=TradeHistoryPage)
def trades_history(
    filters: Annotated[TradeHistoryFilters, Query()],
    db: Session = Depends(get_db),
):
    items, total = trades_service.list_history(db, filters)
    return {
        "items": items,
        "pagination": {
            "total": total,
            "limit": filters.limit,
            "offset": filters.offset,
            "returned": len(items),
            "has_more": filters.offset + len(items) < total,
        },
        "filters": {
            "from": filters.from_,
            "to": filters.to,
            "asset_id": filters.asset_id,
            "status": filters.status,
            "date_field": filters.date_field,
            "sort": filters.sort,
        },
    }


@router.get("/{trade_id}", response_model=TradeRead)
def get_trade(trade_id: int, db: Session = Depends(get_db)):
    try:
        return trades_service.get_trade(db, trade_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{trade_id}/close", response_model=TradeRead)
def close_trade(trade_id: int, payload: TradeClose, db: Session = Depends(get_db)):
    try:
        return trades_service.close_trade(db, trade_id, payload)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{trade_id}/cancel", response_model=TradeRead)
def cancel_trade(trade_id: int, db: Session = Depends(get_db)):
    try:
        return trades_service.cancel_trade(db, trade_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
