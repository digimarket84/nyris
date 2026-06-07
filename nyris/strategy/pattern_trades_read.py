"""Lecture filtrée/paginée + stats des trades PATTERN (read-only ; table pattern_trades)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from nyris.models.asset import Asset
from nyris.models.pattern_trade import PatternTrade
from nyris.schemas.pattern_trade import PatternTradeFilters

_ZERO = Decimal("0.00")
# Majors masqués de l'AFFICHAGE pour les runners intraday/LLM (BDD intacte). Réversible.
# EXCEPTION : le runner trend-following (live-trend-v1) trade les majors -> on les montre.
_HIDDEN = ("BTC", "ETH", "SOL")
_TREND_RUN = "live-trend-v1"


def _conds(f: PatternTradeFilters):
    conds = [or_(Asset.symbol.notin_(_HIDDEN), PatternTrade.run_id == _TREND_RUN)]
    if f.status:
        conds.append(PatternTrade.status == f.status)
    if f.side:
        conds.append(PatternTrade.side == f.side)
    if f.pattern:
        conds.append(PatternTrade.pattern == f.pattern)
    if f.run_id:
        conds.append(PatternTrade.run_id == f.run_id)
    if f.symbol:
        conds.append(Asset.symbol == f.symbol)
    return conds


def list_pattern_trades(db: Session, f: PatternTradeFilters) -> tuple[list[PatternTrade], int]:
    conds = _conds(f)
    count_stmt = select(func.count()).select_from(PatternTrade).join(
        Asset, PatternTrade.asset_id == Asset.id)
    items_stmt = select(PatternTrade, Asset.symbol).join(Asset, PatternTrade.asset_id == Asset.id)
    if conds:
        count_stmt = count_stmt.where(*conds)
        items_stmt = items_stmt.where(*conds)
    total = int(db.scalar(count_stmt) or 0)
    items_stmt = (items_stmt.order_by(PatternTrade.opened_at.desc(), PatternTrade.id.desc())
                  .limit(f.limit).offset(f.offset))
    items: list[PatternTrade] = []
    for trade, symbol in db.execute(items_stmt).all():
        trade.symbol = symbol
        ec = trade.entry_cost or _ZERO
        xc = trade.exit_cost or _ZERO
        fc = trade.funding_cost or _ZERO
        trade.fees_total = ec + xc + fc
        items.append(trade)
    return items, total


def pattern_trades_stats(db: Session, f: PatternTradeFilters) -> dict:
    conds = _conds(f)
    base = select(PatternTrade).join(Asset, PatternTrade.asset_id == Asset.id)
    if conds:
        base = base.where(*conds)
    sub = base.subquery()
    closed = sub.c.status == "closed"

    def cnt(*w):
        return int(db.scalar(select(func.count()).select_from(sub).where(*w)) or 0)

    def net(*w):
        return Decimal(db.scalar(
            select(func.coalesce(func.sum(sub.c.pnl_net), 0)).where(*w)) or 0)

    trades_total = cnt()
    open_count = cnt(sub.c.status == "open")
    closed_count = cnt(closed)
    pnl_gross_total = Decimal(db.scalar(
        select(func.coalesce(func.sum(sub.c.pnl_gross), 0)).where(closed)) or 0)
    pnl_net_total = net(closed)
    fees_total = Decimal(db.scalar(
        select(func.coalesce(func.sum(sub.c.entry_cost), 0)
               + func.coalesce(func.sum(sub.c.exit_cost), 0)
               + func.coalesce(func.sum(sub.c.funding_cost), 0)).where(closed)) or 0)
    wins = cnt(closed, sub.c.pnl_net > 0)
    losses = closed_count - wins
    return {
        "trades_total": trades_total, "open_count": open_count, "closed_count": closed_count,
        "pnl_gross_total": pnl_gross_total, "fees_total": fees_total,
        "pnl_net_total": pnl_net_total, "wins": wins, "losses": losses,
        "win_rate": (wins / closed_count) if closed_count else None,
        "long_count": cnt(closed, sub.c.side == "long"),
        "long_net": net(closed, sub.c.side == "long"),
        "short_count": cnt(closed, sub.c.side == "short"),
        "short_net": net(closed, sub.c.side == "short"),
    }
