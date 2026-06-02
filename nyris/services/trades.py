"""Logique métier des trades simulés : créer, fermer, annuler, lister, historiser."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nyris.core.config import settings
from nyris.core.exceptions import ConflictError, NotFoundError
from nyris.models.asset import Asset
from nyris.models.simulated_trade import SimulatedTrade, TradeStatus
from nyris.schemas.history import HistoryDateField, HistorySort, TradeHistoryFilters
from nyris.schemas.trade import TradeClose, TradeCreate
from nyris.services import pnl

# Mapping filtre/tri -> colonnes (whitelist : pas de tri dynamique arbitraire)
_DATE_COLUMNS = {
    HistoryDateField.opened_at: SimulatedTrade.opened_at,
    HistoryDateField.closed_at: SimulatedTrade.closed_at,
    HistoryDateField.created_at: SimulatedTrade.created_at,
}
_SORT_COLUMNS = {
    HistorySort.opened_at_desc: SimulatedTrade.opened_at.desc(),
    HistorySort.opened_at_asc: SimulatedTrade.opened_at.asc(),
    HistorySort.closed_at_desc: SimulatedTrade.closed_at.desc(),
    HistorySort.closed_at_asc: SimulatedTrade.closed_at.asc(),
    HistorySort.pnl_net_desc: SimulatedTrade.pnl_net.desc(),
    HistorySort.pnl_net_asc: SimulatedTrade.pnl_net.asc(),
    HistorySort.id_desc: SimulatedTrade.id.desc(),
    HistorySort.id_asc: SimulatedTrade.id.asc(),
}


def _get_asset_or_404(db: Session, asset_id: int) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise NotFoundError(f"Asset id={asset_id} introuvable")
    return asset


def get_trade(db: Session, trade_id: int) -> SimulatedTrade:
    trade = db.get(SimulatedTrade, trade_id)
    if trade is None:
        raise NotFoundError(f"Trade id={trade_id} introuvable")
    return trade


def list_trades(
    db: Session,
    status: TradeStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[SimulatedTrade]:
    """Liste simple (endpoint historique existant inchangé)."""
    stmt = select(SimulatedTrade).order_by(SimulatedTrade.id.desc())
    if status is not None:
        stmt = stmt.where(SimulatedTrade.status == status)
    stmt = stmt.limit(limit).offset(offset)
    return list(db.scalars(stmt).all())


def list_history(
    db: Session, filters: TradeHistoryFilters
) -> tuple[list[SimulatedTrade], int]:
    """Historique filtré/paginé. Retourne (items, total) — total hors limit/offset."""
    conditions = []
    date_col = _DATE_COLUMNS[filters.date_field]
    if filters.from_ is not None:
        conditions.append(date_col >= filters.from_)
    if filters.to is not None:
        conditions.append(date_col < filters.to)  # borne haute exclue [from, to)
    if filters.asset_id is not None:
        conditions.append(SimulatedTrade.asset_id == filters.asset_id)
    if filters.status is not None:
        conditions.append(SimulatedTrade.status == filters.status)

    count_stmt = select(func.count()).select_from(SimulatedTrade)
    items_stmt = select(SimulatedTrade)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
        items_stmt = items_stmt.where(*conditions)

    total = int(db.scalar(count_stmt) or 0)
    items_stmt = (
        items_stmt.order_by(_SORT_COLUMNS[filters.sort])
        .limit(filters.limit)
        .offset(filters.offset)
    )
    items = list(db.scalars(items_stmt).all())
    return items, total


def create_trade(db: Session, data: TradeCreate) -> SimulatedTrade:
    asset = _get_asset_or_404(db, data.asset_id)
    if not asset.is_tradeable:
        raise ConflictError(
            f"Asset {asset.symbol} non tradable (status={asset.status.value})"
        )

    entry_fee_rate = (
        data.entry_fee_rate
        if data.entry_fee_rate is not None
        else settings.default_entry_fee_rate
    )
    result = pnl.compute_entry(data.amount_invested, data.entry_price, entry_fee_rate)

    trade = SimulatedTrade(
        asset_id=data.asset_id,
        status=TradeStatus.open,
        amount_invested=data.amount_invested,
        entry_price=data.entry_price,
        quantity=result.quantity,
        fee_model=data.fee_model or settings.default_fee_model,
        fee_currency=data.fee_currency or settings.default_fee_currency,
        entry_fee_rate=entry_fee_rate,
        entry_fee_amount=result.entry_fee_amount,
        notes=data.notes,
        opened_at=datetime.now(UTC),
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


def close_trade(db: Session, trade_id: int, data: TradeClose) -> SimulatedTrade:
    trade = get_trade(db, trade_id)
    if trade.status != TradeStatus.open:
        raise ConflictError(
            f"Impossible de fermer un trade au statut '{trade.status.value}'"
        )

    exit_fee_rate = (
        data.exit_fee_rate
        if data.exit_fee_rate is not None
        else settings.default_exit_fee_rate
    )
    result = pnl.compute_close(
        trade.amount_invested, trade.quantity, data.exit_price, exit_fee_rate
    )

    trade.exit_price = data.exit_price
    trade.exit_fee_rate = exit_fee_rate
    trade.exit_fee_amount = result.exit_fee_amount
    trade.exit_gross_value = result.exit_gross_value
    trade.exit_net_value = result.exit_net_value
    trade.pnl_net = result.pnl_net
    trade.pnl_percent = result.pnl_percent
    trade.status = TradeStatus.closed
    trade.closed_at = datetime.now(UTC)

    db.commit()
    db.refresh(trade)
    return trade


def cancel_trade(db: Session, trade_id: int) -> SimulatedTrade:
    trade = get_trade(db, trade_id)
    if trade.status not in (TradeStatus.open, TradeStatus.draft):
        raise ConflictError(
            f"Impossible d'annuler un trade au statut '{trade.status.value}'"
        )
    trade.status = TradeStatus.cancelled
    db.commit()
    db.refresh(trade)
    return trade
