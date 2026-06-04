"""Lecture filtrée/paginée + stats des trades SHORT (read-only).

Source de vérité : table `short_trades` UNIQUEMENT. Ne touche jamais
`simulated_trades` : aucun mélange baseline/short possible ici.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nyris.models.asset import Asset
from nyris.models.short_trade import ShortTrade
from nyris.schemas.short_trade import ShortTradeFilters

_ZERO = Decimal("0.00")


def _conds(filters: ShortTradeFilters):
    conds = []
    if filters.status:
        conds.append(ShortTrade.status == filters.status)
    if filters.run_id:
        conds.append(ShortTrade.run_id == filters.run_id)
    if filters.symbol:
        conds.append(Asset.symbol == filters.symbol)
    return conds


def list_short_trades(db: Session, filters: ShortTradeFilters) -> tuple[list[ShortTrade], int]:
    conds = _conds(filters)

    count_stmt = (
        select(func.count())
        .select_from(ShortTrade)
        .join(Asset, ShortTrade.asset_id == Asset.id)
    )
    items_stmt = (
        select(ShortTrade, Asset.symbol).join(Asset, ShortTrade.asset_id == Asset.id)
    )
    if conds:
        count_stmt = count_stmt.where(*conds)
        items_stmt = items_stmt.where(*conds)

    total = int(db.scalar(count_stmt) or 0)
    items_stmt = (
        items_stmt.order_by(ShortTrade.opened_at.desc(), ShortTrade.id.desc())
        .limit(filters.limit)
        .offset(filters.offset)
    )

    items: list[ShortTrade] = []
    for trade, symbol in db.execute(items_stmt).all():
        trade.symbol = symbol  # attribut transient (non persisté)
        ec = trade.entry_cost or _ZERO
        xc = trade.exit_cost or _ZERO
        fc = trade.funding_cost or _ZERO
        trade.fees_total = ec + xc + fc
        items.append(trade)
    return items, total


def short_trades_stats(db: Session, filters: ShortTradeFilters) -> dict:
    conds = _conds(filters)
    base = select(ShortTrade).join(Asset, ShortTrade.asset_id == Asset.id)
    if conds:
        base = base.where(*conds)
    sub = base.subquery()

    trades_total = int(db.scalar(select(func.count()).select_from(sub)) or 0)
    open_count = int(
        db.scalar(select(func.count()).select_from(sub).where(sub.c.status == "open")) or 0
    )

    closed = sub.c.status == "closed"
    closed_count = int(db.scalar(select(func.count()).select_from(sub).where(closed)) or 0)
    pnl_gross_total = Decimal(
        db.scalar(select(func.coalesce(func.sum(sub.c.pnl_gross), 0)).where(closed)) or 0
    )
    pnl_net_total = Decimal(
        db.scalar(select(func.coalesce(func.sum(sub.c.pnl_net), 0)).where(closed)) or 0
    )
    fees_total = Decimal(
        db.scalar(
            select(
                func.coalesce(func.sum(sub.c.entry_cost), 0)
                + func.coalesce(func.sum(sub.c.exit_cost), 0)
                + func.coalesce(func.sum(sub.c.funding_cost), 0)
            ).where(closed)
        )
        or 0
    )
    wins = int(
        db.scalar(select(func.count()).select_from(sub).where(closed, sub.c.pnl_net > 0)) or 0
    )
    losses = closed_count - wins
    win_rate = (wins / closed_count) if closed_count else None

    return {
        "trades_total": trades_total,
        "open_count": open_count,
        "closed_count": closed_count,
        "pnl_gross_total": pnl_gross_total,
        "fees_total": fees_total,
        "pnl_net_total": pnl_net_total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
    }
