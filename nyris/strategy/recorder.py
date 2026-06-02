"""Couche d'orchestration : journalise les décisions de stratégie.

Strictement séparée du moteur pur : `engine.evaluate()` / `_decide()` ne sont
PAS modifiés et n'ont aucun effet de bord. Le recorder lit une `Decision` (pure)
et la persiste dans `strategy_decisions`, de façon idempotente.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nyris.models.asset import Asset
from nyris.models.strategy_decision import StrategyDecision
from nyris.strategy.engine import evaluate
from nyris.strategy.models import Decision, PositionState, StrategyParams


def evaluated_at_from_candle(candle_close_time_ms: int) -> datetime:
    """Temps logique dérivé de la bougie source (aucune horloge système)."""
    return datetime.fromtimestamp(candle_close_time_ms / 1000, tz=UTC)


def build_decision_record(
    asset: Asset,
    params: StrategyParams,
    decision: Decision,
    position_state: str,
    run_id: str | None = None,
    simulated_trade_id: int | None = None,
) -> StrategyDecision:
    """Mapping PUR Decision -> ligne (testable sans DB)."""
    snap = decision.snapshot
    return StrategyDecision(
        evaluated_at=evaluated_at_from_candle(snap.candle_close_time),
        asset_id=asset.id,
        symbol=asset.symbol,
        timeframe=params.timeframe,
        candle_close_time=snap.candle_close_time,
        close_price=snap.close,
        ema_fast=snap.ema_fast,
        ema_slow=snap.ema_slow,
        ema_trend=snap.ema_trend,
        atr=snap.atr,
        action=decision.action.value,
        reason=decision.reason.value,
        position_state=position_state,
        entry_price=decision.entry,
        stop_price=decision.stop,
        take_profit_price=decision.take_profit,
        params_key=params.key(),
        run_id=run_id,
        simulated_trade_id=simulated_trade_id,
    )


def _find_existing(db: Session, asset_id: int, params: StrategyParams, candle_close_time: int):
    return db.scalar(
        select(StrategyDecision).where(
            StrategyDecision.asset_id == asset_id,
            StrategyDecision.timeframe == params.timeframe,
            StrategyDecision.candle_close_time == candle_close_time,
            StrategyDecision.params_key == params.key(),
        )
    )


def record_decision(
    db: Session,
    asset: Asset,
    params: StrategyParams,
    decision: Decision,
    position_state: str,
    run_id: str | None = None,
    simulated_trade_id: int | None = None,
) -> StrategyDecision:
    """Persiste la décision. Idempotent : même (asset, tf, bougie, params) -> pas de doublon."""
    cct = decision.snapshot.candle_close_time
    existing = _find_existing(db, asset.id, params, cct)
    if existing is not None:
        return existing

    rec = build_decision_record(
        asset, params, decision, position_state, run_id, simulated_trade_id
    )
    db.add(rec)
    try:
        db.commit()
    except IntegrityError:  # course éventuelle : la contrainte d'unicité a joué
        db.rollback()
        return _find_existing(db, asset.id, params, cct)
    db.refresh(rec)
    return rec


def record_evaluation(
    db: Session,
    asset: Asset,
    candles: list,
    position: PositionState | None,
    params: StrategyParams,
    run_id: str | None = None,
) -> StrategyDecision:
    """Convenience : evaluate() PUR puis journalisation (jonction moteur+DB)."""
    decision = evaluate(candles, position, params)
    position_state = "open" if position is not None else "flat"
    return record_decision(db, asset, params, decision, position_state, run_id=run_id)
