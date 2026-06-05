"""Runner PATTERN (oneshot, paper-only, bidirectionnel) — détection 5m.

Scanne les 13 actifs, détecte cassure Donchian / pullback EMA (long OU short) et ouvre
des trades dans `pattern_trades`. Journalise chaque décision dans `strategy_decisions`
(idempotent par params_key/timeframe/bougie). Lock/run_id dédiés. N'importe ni ne
modifie le baseline ni le short ; ne touche jamais simulated_trades / short_trades.

Exécution : python -m nyris.strategy.pattern_runner
"""

from __future__ import annotations

import fcntl
import logging
from contextlib import contextmanager
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nyris.models.asset import Asset
from nyris.models.pattern_trade import PatternTrade
from nyris.models.strategy_decision import StrategyDecision
from nyris.services import candles as candles_service
from nyris.services.binance import BinanceError
from nyris.strategy import pattern_pnl
from nyris.strategy.models import Action
from nyris.strategy.pattern_engine import evaluate, warmup
from nyris.strategy.pattern_models import PatternParams, PatternPosition, PatternReason
from nyris.strategy.recorder import evaluated_at_from_candle

logger = logging.getLogger("nyris.pattern_runner")

PAT = PatternParams()
EXEC_LIMIT = 320
LOCK_PATH = "/srv/nyris/pattern-runner.lock"
_TF_HOURS = {"1m": 1 / 60, "5m": 5 / 60, "15m": 0.25, "1h": 1.0, "4h": 4.0}


class PatternRunnerBusy(Exception):
    pass


@contextmanager
def cycle_lock(path: str = LOCK_PATH):
    fh = open(path, "w")  # noqa: SIM115
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        fh.close()
        raise PatternRunnerBusy() from exc
    try:
        yield
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def _tf_hours(tf: str) -> float:
    return _TF_HOURS.get(tf, 5 / 60)


def _bump(s: dict, k: str) -> None:
    s[k] = s.get(k, 0) + 1


def _decision_exists(db: Session, asset_id: int, p: PatternParams, cct: int) -> bool:
    return db.scalar(
        select(StrategyDecision.id).where(
            StrategyDecision.asset_id == asset_id,
            StrategyDecision.timeframe == p.timeframe,
            StrategyDecision.candle_close_time == cct,
            StrategyDecision.params_key == p.key(),
        )
    ) is not None


def _open_trade(db: Session, asset_id: int) -> PatternTrade | None:
    return db.scalar(
        select(PatternTrade).where(PatternTrade.asset_id == asset_id, PatternTrade.status == "open")
        .order_by(PatternTrade.id.desc())
    )


def _open_count(db: Session) -> int:
    return int(db.scalar(
        select(func.count()).select_from(PatternTrade).where(PatternTrade.status == "open")) or 0)


def _open_exposure(db: Session) -> Decimal:
    return Decimal(db.scalar(
        select(func.coalesce(func.sum(PatternTrade.amount_invested), 0))
        .where(PatternTrade.status == "open")))


def _last_closed(db: Session, asset_id: int) -> PatternTrade | None:
    return db.scalar(
        select(PatternTrade)
        .where(PatternTrade.asset_id == asset_id, PatternTrade.status == "closed")
        .order_by(PatternTrade.id.desc()))


def _record(db, asset, p, decision, pstate, trade_id=None):
    snap = decision.snapshot
    rec = StrategyDecision(
        evaluated_at=evaluated_at_from_candle(snap.candle_close_time), asset_id=asset.id,
        symbol=asset.symbol, timeframe=p.timeframe, candle_close_time=snap.candle_close_time,
        close_price=snap.close, ema_fast=snap.ema_fast, ema_slow=snap.ema_slow,
        ema_trend=snap.ema_trend, atr=snap.atr, action=decision.action.value,
        reason=decision.reason.value, position_state=pstate, entry_price=decision.entry,
        stop_price=decision.stop, take_profit_price=decision.take_profit, params_key=p.key(),
        run_id=p.run_id,
        notes=(f"{decision.side or ''}:{decision.pattern or ''}"
               + (f":pattern_trade:{trade_id}" if trade_id else "")),
    )
    db.add(rec)


def _atr_pct(decision) -> float | None:
    s = decision.snapshot
    if s.atr is None or s.close is None or float(s.close) == 0:
        return None
    return float(s.atr) / float(s.close)


def _entry_guard(db, asset, p: PatternParams, cct: int, atr_pct) -> PatternReason | None:
    if _open_count(db) >= p.max_open_positions:
        return PatternReason.skip_blocked_max_positions
    notional = p.starting_capital * p.position_fraction
    if _open_exposure(db) + notional > p.starting_capital * p.max_total_exposure:
        return PatternReason.skip_blocked_exposure
    last = _last_closed(db, asset.id)
    if last is not None and last.closed_at is not None:
        tf_ms = _tf_hours(p.timeframe) * 3600 * 1000
        if (cct - int(last.closed_at.timestamp() * 1000)) / tf_ms < p.cooldown:
            return PatternReason.skip_blocked_cooldown
    if notional < p.min_notional:
        return PatternReason.skip_blocked_min_notional
    if atr_pct is not None and (atr_pct > p.max_atr_pct or atr_pct < p.min_atr_pct):
        return PatternReason.skip_blocked_volatility
    return None


def _build(asset, p: PatternParams, decision, cct) -> PatternTrade:
    notional = (p.starting_capital * p.position_fraction).quantize(Decimal("0.01"))
    res = pattern_pnl.compute_entry(notional, decision.entry, p)
    return PatternTrade(
        asset_id=asset.id, status="open", side=decision.side, pattern=decision.pattern,
        amount_invested=notional, entry_price=decision.entry, quantity=res.quantity,
        stop_price=decision.stop, take_profit_price=decision.take_profit,
        commission_rate=p.commission_rate, spread_rate=p.spread_rate,
        slippage_rate=p.slippage_rate, funding_rate_daily=p.funding_rate_daily,
        entry_cost=res.entry_cost, entry_reason=decision.reason.value, run_id=p.run_id,
        params_key=p.key(), notes="auto:pattern-runner", opened_at=evaluated_at_from_candle(cct),
    )


def _close(trade: PatternTrade, p: PatternParams, decision, cct) -> None:
    opened_ms = int(trade.opened_at.timestamp() * 1000)
    hours = max((cct - opened_ms) / 3_600_000, 0.0)
    res = pattern_pnl.compute_close(
        trade.side, trade.amount_invested, trade.quantity, trade.entry_cost,
        decision.snapshot.close, p, hours)
    trade.exit_price = decision.snapshot.close
    trade.exit_cost = res.exit_cost
    trade.funding_cost = res.funding_cost
    trade.pnl_gross = res.pnl_gross
    trade.pnl_net = res.pnl_net
    trade.pnl_percent = res.pnl_percent
    trade.exit_reason = decision.reason.value
    trade.status = "closed"
    trade.closed_at = evaluated_at_from_candle(cct)


def process_asset(db: Session, symbol: str, p: PatternParams, summary: dict) -> None:
    asset = db.scalar(select(Asset).where(Asset.symbol == symbol))
    if asset is None or not asset.is_tradeable or not asset.binance_symbol:
        _bump(summary, "ineligible")
        return
    try:
        candles = candles_service.get_candles(asset.binance_symbol, p.timeframe, EXEC_LIMIT)
    except BinanceError as exc:
        logger.warning("%s: données indisponibles (%s)", symbol, exc)
        _bump(summary, "data_error")
        return
    if len(candles) < warmup(p) + 1:
        _bump(summary, "fail_safe")
        return
    cct = candles[-1].close_time
    if _decision_exists(db, asset.id, p, cct):
        _bump(summary, "already_processed")
        return

    trade = _open_trade(db, asset.id)
    pos = None
    if trade is not None:
        pos = PatternPosition(side=trade.side, entry=trade.entry_price, stop=trade.stop_price,
                              take_profit=trade.take_profit_price)
    decision = evaluate(candles, pos, p)
    pstate = "open" if trade is not None else "flat"

    if decision.action == Action.enter:
        blocked = _entry_guard(db, asset, p, cct, _atr_pct(decision))
        if blocked is not None:
            from dataclasses import replace
            _record(db, asset, p, replace(decision, action=Action.skip, reason=blocked), pstate)
            db.commit()
            _bump(summary, blocked.value)
            return
        nt = _build(asset, p, decision, cct)
        db.add(nt)
        db.flush()
        _record(db, asset, p, decision, pstate, trade_id=nt.id)
        db.commit()
        _bump(summary, "enter_" + (decision.side or "?"))
    elif decision.action == Action.exit and trade is not None:
        _close(trade, p, decision, cct)
        db.flush()
        _record(db, asset, p, decision, pstate, trade_id=trade.id)
        db.commit()
        _bump(summary, "exit")
    else:
        _record(db, asset, p, decision, pstate, trade_id=trade.id if trade else None)
        db.commit()
        _bump(summary, "hold_skip")


def run_cycle(db: Session, p: PatternParams | None = None) -> dict:
    p = p or PAT
    summary: dict = {"run_id": p.run_id}
    for symbol in p.universe:
        try:
            process_asset(db, symbol, p, summary)
        except Exception:
            db.rollback()
            logger.exception("erreur pattern sur %s", symbol)
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
            logger.info("cycle pattern terminé: %s", summary)
            print(json.dumps(summary, ensure_ascii=False))
    except PatternRunnerBusy:
        logger.warning("un autre cycle pattern est en cours, abandon")
        print('{"status": "busy"}')


if __name__ == "__main__":
    _main()
