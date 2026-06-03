"""Runner challenger SHORT (oneshot, paper-only) — totalement parallèle au baseline.

Isolation : table `short_trades` (jamais `simulated_trades`), lock dédié, run_id
dédié, logs dédiés, params_key short. Réutilise les briques pures + le recorder
(décisions dans `strategy_decisions`, isolées par params_key/run_id). Le runner
baseline n'est NI importé NI modifié.

Exécution : python -m nyris.strategy.short_runner
"""

from __future__ import annotations

import fcntl
import logging
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nyris.models.asset import Asset
from nyris.models.short_trade import ShortTrade
from nyris.models.strategy_decision import StrategyDecision
from nyris.services import candles as candles_service
from nyris.services.binance import BinanceError
from nyris.strategy import short_pnl
from nyris.strategy.models import Action, PositionState
from nyris.strategy.recorder import build_decision_record, evaluated_at_from_candle
from nyris.strategy.short_engine import evaluate_short, warmup
from nyris.strategy.short_models import ShortParams, ShortReason

logger = logging.getLogger("nyris.short_runner")

SHORT = ShortParams()
CANDLE_LIMIT = 300
LOCK_PATH = "/srv/nyris/short-runner.lock"

_TF_HOURS = {"1h": 1.0, "2h": 2.0, "4h": 4.0, "1d": 24.0}


class ShortRunnerBusy(Exception):
    """Un autre cycle short runner est déjà en cours."""


@contextmanager
def cycle_lock(path: str = LOCK_PATH):
    fh = open(path, "w")  # noqa: SIM115
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        fh.close()
        raise ShortRunnerBusy() from exc
    try:
        yield
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def _tf_hours(tf: str) -> float:
    return _TF_HOURS.get(tf, 4.0)


# ---- lectures DB (table short_trades UNIQUEMENT) ----
def _decision_exists(db: Session, asset_id: int, params: ShortParams, cct: int) -> bool:
    return (
        db.scalar(
            select(StrategyDecision.id).where(
                StrategyDecision.asset_id == asset_id,
                StrategyDecision.timeframe == params.timeframe,
                StrategyDecision.candle_close_time == cct,
                StrategyDecision.params_key == params.key(),
            )
        )
        is not None
    )


def _open_short(db: Session, asset_id: int) -> ShortTrade | None:
    return db.scalar(
        select(ShortTrade)
        .where(ShortTrade.asset_id == asset_id, ShortTrade.status == "open")
        .order_by(ShortTrade.id.desc())
    )


def _open_count(db: Session) -> int:
    return int(
        db.scalar(select(func.count()).select_from(ShortTrade).where(ShortTrade.status == "open"))
        or 0
    )


def _open_exposure(db: Session) -> Decimal:
    return Decimal(
        db.scalar(
            select(func.coalesce(func.sum(ShortTrade.amount_invested), 0)).where(
                ShortTrade.status == "open"
            )
        )
    )


def _last_closed(db: Session, asset_id: int) -> ShortTrade | None:
    return db.scalar(
        select(ShortTrade)
        .where(ShortTrade.asset_id == asset_id, ShortTrade.status == "closed")
        .order_by(ShortTrade.id.desc())
    )


# ---- métier ----
def _position_state(trade: ShortTrade, candles: list, params: ShortParams) -> PositionState:
    opened_ms = int(trade.opened_at.timestamp() * 1000)
    bars = sum(1 for c in candles if c.close_time > opened_ms)
    stop = trade.stop_price if trade.stop_price is not None else Decimal("1e12")
    tp = trade.take_profit_price if trade.take_profit_price is not None else Decimal("0")
    return PositionState(entry_price=trade.entry_price, stop=stop, take_profit=tp, bars_held=bars)


def _entry_guard(db: Session, asset: Asset, params: ShortParams, cct: int) -> ShortReason | None:
    if _open_count(db) >= params.max_open_positions:
        return ShortReason.skip_blocked_max_positions
    notional = params.starting_capital * params.position_fraction
    cap = params.starting_capital * params.max_total_exposure
    if _open_exposure(db) + notional > cap:
        return ShortReason.skip_blocked_exposure
    last = _last_closed(db, asset.id)
    if last is not None and last.closed_at is not None:
        tf_ms = _tf_hours(params.timeframe) * 3600 * 1000
        if (cct - int(last.closed_at.timestamp() * 1000)) / tf_ms < params.cooldown:
            return ShortReason.skip_blocked_cooldown
    if notional < params.min_notional:
        return ShortReason.skip_blocked_min_notional
    return None


def _build_short(asset: Asset, params: ShortParams, decision, cct: int) -> ShortTrade:
    notional = (params.starting_capital * params.position_fraction).quantize(Decimal("0.01"))
    res = short_pnl.compute_short_entry(notional, decision.entry, params)
    return ShortTrade(
        asset_id=asset.id,
        status="open",
        side="short",
        amount_invested=notional,
        entry_price=decision.entry,
        quantity=res.quantity,
        stop_price=decision.stop,
        take_profit_price=decision.take_profit,
        commission_rate=params.commission_rate,
        spread_rate=params.spread_rate,
        slippage_rate=params.slippage_rate,
        funding_rate_daily=params.funding_rate_daily,
        entry_cost=res.entry_cost,
        run_id=params.run_id,
        params_key=params.key(),
        notes="auto:short-runner",
        opened_at=evaluated_at_from_candle(cct),
    )


def _close_short(
    trade: ShortTrade, params: ShortParams, decision, bars_held: int, cct: int
) -> None:
    res = short_pnl.compute_short_close(
        trade.amount_invested,
        trade.quantity,
        trade.entry_cost,
        decision.snapshot.close,
        params,
        bars_held,
        _tf_hours(params.timeframe),
    )
    trade.exit_price = decision.snapshot.close
    trade.exit_cost = res.exit_cost
    trade.funding_cost = res.funding_cost
    trade.pnl_gross = res.pnl_gross
    trade.pnl_net = res.pnl_net
    trade.pnl_percent = res.pnl_percent
    trade.status = "closed"
    trade.closed_at = evaluated_at_from_candle(cct)


def _bump(summary: dict, key: str) -> None:
    summary[key] = summary.get(key, 0) + 1


def _record(db, asset, params, decision, pstate, short_trade_id=None):
    rec = build_decision_record(asset, params, decision, pstate, run_id=params.run_id)
    if short_trade_id is not None:
        rec.notes = f"short_trade:{short_trade_id}"
    db.add(rec)


def process_asset(db: Session, symbol: str, params: ShortParams, summary: dict) -> None:
    asset = db.scalar(select(Asset).where(Asset.symbol == symbol))
    if asset is None or not asset.is_tradeable or not asset.binance_symbol:
        _bump(summary, "ineligible")
        return

    try:
        candles = candles_service.get_candles(asset.binance_symbol, params.timeframe, CANDLE_LIMIT)
    except BinanceError as exc:
        logger.warning("%s: données indisponibles (%s)", symbol, exc)
        _bump(summary, "data_error")
        return

    if len(candles) < warmup(params) + 1:
        _bump(summary, "fail_safe")
        return

    cct = candles[-1].close_time
    if _decision_exists(db, asset.id, params, cct):
        _bump(summary, "already_processed")
        return

    trade = _open_short(db, asset.id)
    position = _position_state(trade, candles, params) if trade is not None else None
    decision = evaluate_short(candles, position, params)
    pstate = "open" if trade is not None else "flat"

    if decision.action == Action.enter:
        blocked = _entry_guard(db, asset, params, cct)
        if blocked is not None:
            _record(
                db, asset, params, replace(decision, action=Action.skip, reason=blocked), pstate
            )
            db.commit()
            _bump(summary, blocked.value)
            return
        new_trade = _build_short(asset, params, decision, cct)
        db.add(new_trade)
        db.flush()
        _record(db, asset, params, decision, pstate, short_trade_id=new_trade.id)
        db.commit()
        _bump(summary, "enter")
    elif decision.action == Action.exit and trade is not None:
        _close_short(trade, params, decision, position.bars_held, cct)
        db.flush()
        _record(db, asset, params, decision, pstate, short_trade_id=trade.id)
        db.commit()
        _bump(summary, "exit")
    else:
        _record(db, asset, params, decision, pstate)
        db.commit()
        _bump(summary, "hold_skip")


def run_cycle(db: Session, params: ShortParams | None = None) -> dict:
    params = params or SHORT
    summary: dict = {"run_id": params.run_id}
    for symbol in params.universe:
        try:
            process_asset(db, symbol, params, summary)
        except Exception:
            db.rollback()
            logger.exception("erreur lors du traitement short de %s", symbol)
            _bump(summary, "errors")
    return summary


def _main() -> None:
    import json

    from nyris.core.database import SessionLocal
    from nyris.core.logging import configure_logging

    configure_logging()
    try:
        with cycle_lock():
            with SessionLocal() as db:
                summary = run_cycle(db)
            logger.info("cycle short terminé: %s", summary)
            print(json.dumps(summary, ensure_ascii=False))
    except ShortRunnerBusy:
        logger.warning("un autre cycle short runner est en cours, abandon")
        print('{"status": "busy"}')


if __name__ == "__main__":
    _main()
