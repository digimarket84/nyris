"""Lecture filtrée/paginée des décisions de stratégie (read-only)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nyris.models.strategy_decision import StrategyDecision
from nyris.schemas.strategy_decision import StrategyDecisionFilters


def list_decisions(
    db: Session, filters: StrategyDecisionFilters
) -> tuple[list[StrategyDecision], int]:
    conds = []
    if filters.run_id:
        conds.append(StrategyDecision.run_id == filters.run_id)
    if filters.asset_id:
        conds.append(StrategyDecision.asset_id == filters.asset_id)
    if filters.symbol:
        conds.append(StrategyDecision.symbol == filters.symbol)
    if filters.timeframe:
        conds.append(StrategyDecision.timeframe == filters.timeframe)
    if filters.action:
        conds.append(StrategyDecision.action == filters.action)
    if filters.reason:
        conds.append(StrategyDecision.reason == filters.reason)
    if filters.position_state:
        conds.append(StrategyDecision.position_state == filters.position_state)
    if filters.from_ is not None:
        conds.append(StrategyDecision.evaluated_at >= filters.from_)
    if filters.to is not None:
        conds.append(StrategyDecision.evaluated_at < filters.to)  # borne haute exclue

    count_stmt = select(func.count()).select_from(StrategyDecision)
    items_stmt = select(StrategyDecision)
    if conds:
        count_stmt = count_stmt.where(*conds)
        items_stmt = items_stmt.where(*conds)

    total = int(db.scalar(count_stmt) or 0)
    items_stmt = (
        items_stmt.order_by(
            StrategyDecision.evaluated_at.desc(), StrategyDecision.id.desc()
        )
        .limit(filters.limit)
        .offset(filters.offset)
    )
    items = list(db.scalars(items_stmt).all())
    return items, total
