"""Runner TREND-FOLLOWING daily (oneshot, paper, long-only) — exécution 1×/jour.

Pour chaque actif : cassure Donchian haut -> ouvre un long ; cassure Donchian bas ->
clôture. Stocke dans `pattern_trades` (run_id=live-trend-v1, pattern='trend', side='long',
SANS stop/TP -> le pattern_monitor l'ignore, le runner gère la sortie). Journalise dans
strategy_decisions (idempotent par jour). Isolé ; baseline gelé ; ne touche pas les autres runs.

Exécution : python -m nyris.strategy.trend_runner
"""

from __future__ import annotations

import fcntl
import logging
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from nyris.models.asset import Asset
from nyris.models.pattern_trade import PatternTrade
from nyris.models.strategy_decision import StrategyDecision
from nyris.services import candles as candles_service
from nyris.services.binance import BinanceError
from nyris.strategy import pattern_pnl
from nyris.strategy.recorder import evaluated_at_from_candle
from nyris.strategy.trend_engine import evaluate_trend, warmup
from nyris.strategy.trend_models import TrendParams

logger = logging.getLogger("nyris.trend_runner")
TREND = TrendParams()
CANDLE_LIMIT = 200
LOCK_PATH = "/srv/nyris/trend-runner.lock"


class TrendRunnerBusy(Exception):
    pass


@contextmanager
def cycle_lock(path: str = LOCK_PATH):
    fh = open(path, "w")  # noqa: SIM115
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        fh.close()
        raise TrendRunnerBusy() from exc
    try:
        yield
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def _bump(s, k):
    s[k] = s.get(k, 0) + 1


def _open(db, asset_id, p):
    return db.scalar(select(PatternTrade).where(
        PatternTrade.asset_id == asset_id, PatternTrade.run_id == p.run_id,
        PatternTrade.status == "open").order_by(PatternTrade.id.desc()))


def _decision_exists(db, asset_id, p, cct):
    return db.scalar(select(StrategyDecision.id).where(
        StrategyDecision.asset_id == asset_id, StrategyDecision.timeframe == p.timeframe,
        StrategyDecision.candle_close_time == cct,
        StrategyDecision.params_key == p.key())) is not None


def _record(db, asset, p, d, pstate, trade_id=None):
    db.add(StrategyDecision(
        evaluated_at=evaluated_at_from_candle(d.cct), asset_id=asset.id, symbol=asset.symbol,
        timeframe=p.timeframe, candle_close_time=d.cct, close_price=d.close,
        ema_trend=d.dch, ema_fast=d.dcl, action=d.action, reason=d.reason.value,
        position_state=pstate, entry_price=d.entry, params_key=p.key(), run_id=p.run_id,
        notes=(f"trend:pattern_trade:{trade_id}" if trade_id else None)))


def _build(asset, p, d):
    res = pattern_pnl.compute_entry(p.per_position, d.entry, p)
    return PatternTrade(
        asset_id=asset.id, status="open", side="long", pattern="trend",
        amount_invested=p.per_position, entry_price=d.entry, quantity=res.quantity,
        stop_price=None, take_profit_price=None,  # sortie au cross Donchian (runner, pas monitor)
        commission_rate=p.commission_rate, spread_rate=p.spread_rate,
        slippage_rate=p.slippage_rate, funding_rate_daily=p.funding_rate_daily,
        entry_cost=res.entry_cost, entry_reason=d.reason.value, run_id=p.run_id,
        params_key=p.key(), notes="auto:trend-runner", opened_at=evaluated_at_from_candle(d.cct))


def _close(trade, p, d):
    opened_ms = int(trade.opened_at.timestamp() * 1000)
    hours = max((d.cct - opened_ms) / 3_600_000, 0.0)
    res = pattern_pnl.compute_close("long", trade.amount_invested, trade.quantity,
                                    trade.entry_cost, d.close, p, hours)
    trade.exit_price = d.close
    trade.exit_cost = res.exit_cost
    trade.funding_cost = res.funding_cost
    trade.pnl_gross = res.pnl_gross
    trade.pnl_net = res.pnl_net
    trade.pnl_percent = res.pnl_percent
    trade.exit_reason = d.reason.value
    trade.status = "closed"
    trade.closed_at = evaluated_at_from_candle(d.cct)


def process_asset(db: Session, symbol: str, p: TrendParams, summary: dict) -> None:
    asset = db.scalar(select(Asset).where(Asset.symbol == symbol))
    if asset is None or not asset.is_tradeable or not asset.binance_symbol:
        _bump(summary, "ineligible")
        return
    try:
        candles = candles_service.get_candles(asset.binance_symbol, p.timeframe, CANDLE_LIMIT)
    except BinanceError as exc:
        logger.warning("%s: données indisponibles (%s)", symbol, exc)
        _bump(summary, "data_error")
        return
    if len(candles) < warmup(p) + 1:
        _bump(summary, "fail_safe")
        return
    trade = _open(db, asset.id, p)
    cct = candles[-1].close_time
    if _decision_exists(db, asset.id, p, cct):
        _bump(summary, "already_processed")
        return
    d = evaluate_trend(candles, trade is not None, p)
    pstate = "open" if trade is not None else "flat"
    if d.action == "enter":
        nt = _build(asset, p, d)
        db.add(nt)
        db.flush()
        _record(db, asset, p, d, pstate, trade_id=nt.id)
        db.commit()
        _bump(summary, "enter")
    elif d.action == "exit" and trade is not None:
        _close(trade, p, d)
        db.flush()
        _record(db, asset, p, d, pstate, trade_id=trade.id)
        db.commit()
        _bump(summary, "exit")
    else:
        _record(db, asset, p, d, pstate, trade_id=trade.id if trade else None)
        db.commit()
        _bump(summary, d.reason.value)


def run_cycle(db: Session, p: TrendParams | None = None) -> dict:
    p = p or TREND
    summary: dict = {"run_id": p.run_id}
    for sym in p.universe:
        try:
            process_asset(db, sym, p, summary)
        except Exception:
            db.rollback()
            logger.exception("erreur trend sur %s", sym)
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
            logger.info("cycle trend terminé: %s", summary)
            print(json.dumps(summary, ensure_ascii=False))
    except TrendRunnerBusy:
        logger.warning("un autre cycle trend est en cours, abandon")
        print('{"status": "busy"}')


if __name__ == "__main__":
    _main()
