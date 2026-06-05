"""Gardien temps réel des positions PATTERN (oneshot, 1m, bidirectionnel).

Surveille pattern_trades ouverts chaque minute sur bougies 1m et déclenche stop/TP
au NIVEAU EXACT (high/low intra-bougie), selon le sens :
  - long  : low <= stop -> stop ; high >= tp -> take-profit
  - short : high >= stop -> stop ; low <= tp -> take-profit
Fermeture gardée (UPDATE ... WHERE status='open'). N'ouvre aucun trade.

Exécution : python -m nyris.strategy.pattern_monitor
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from nyris.models.asset import Asset
from nyris.models.pattern_trade import PatternTrade
from nyris.services import candles as candles_service
from nyris.services.binance import BinanceError
from nyris.strategy import pattern_pnl
from nyris.strategy.pattern_runner import PatternRunnerBusy, cycle_lock
from nyris.strategy.recorder import evaluated_at_from_candle

logger = logging.getLogger("nyris.pattern_monitor")

LOCK_PATH = "/srv/nyris/pattern-monitor.lock"
MONITOR_TF = "1m"
CANDLE_LIMIT = 5


def _bump(s: dict, k: str) -> None:
    s[k] = s.get(k, 0) + 1


def _rates(t: PatternTrade):
    return SimpleNamespace(commission_rate=t.commission_rate, spread_rate=t.spread_rate,
                           slippage_rate=t.slippage_rate, funding_rate_daily=t.funding_rate_daily)


def _close_exact(db: Session, t: PatternTrade, exit_price, reason: str, cct: int) -> bool:
    opened_ms = int(t.opened_at.timestamp() * 1000)
    hours = max((cct - opened_ms) / 3_600_000, 0.0)
    res = pattern_pnl.compute_close(t.side, t.amount_invested, t.quantity, t.entry_cost,
                                    exit_price, _rates(t), hours)
    r = db.execute(
        update(PatternTrade).where(PatternTrade.id == t.id, PatternTrade.status == "open").values(
            status="closed", exit_price=exit_price, exit_cost=res.exit_cost,
            funding_cost=res.funding_cost, pnl_gross=res.pnl_gross, pnl_net=res.pnl_net,
            pnl_percent=res.pnl_percent, exit_reason=reason,
            closed_at=evaluated_at_from_candle(cct), notes=(t.notes or "") + ";monitor:exact"))
    db.commit()
    return r.rowcount == 1


def process_trade(db: Session, t: PatternTrade, binance_symbol: str | None, summary: dict) -> None:
    if not binance_symbol:
        _bump(summary, "ineligible")
        return
    try:
        candles = candles_service.get_candles(binance_symbol, MONITOR_TF, CANDLE_LIMIT)
    except BinanceError:
        _bump(summary, "data_error")
        return
    if not candles:
        _bump(summary, "no_data")
        return
    last = candles[-1]
    cct = last.close_time
    hi, lo = float(last.high), float(last.low)
    stop = float(t.stop_price) if t.stop_price is not None else None
    tp = float(t.take_profit_price) if t.take_profit_price is not None else None

    exit_price = reason = None
    if t.side == "long":
        if stop is not None and lo <= stop:
            exit_price, reason = t.stop_price, "exit_stop"
        elif tp is not None and hi >= tp:
            exit_price, reason = t.take_profit_price, "exit_take_profit"
    else:  # short
        if stop is not None and hi >= stop:
            exit_price, reason = t.stop_price, "exit_stop"
        elif tp is not None and lo <= tp:
            exit_price, reason = t.take_profit_price, "exit_take_profit"

    if exit_price is None:
        _bump(summary, "watch")
    elif _close_exact(db, t, exit_price, reason, cct):
        _bump(summary, reason)
    else:
        _bump(summary, "already_closed")


def run_cycle(db: Session) -> dict:
    summary: dict = {"runner": "pattern-monitor"}
    opens = db.execute(
        select(PatternTrade, Asset.binance_symbol)
        .join(Asset, PatternTrade.asset_id == Asset.id)
        .where(PatternTrade.status == "open")).all()
    for t, bsym in opens:
        try:
            process_trade(db, t, bsym, summary)
        except Exception:
            db.rollback()
            logger.exception("erreur monitor pattern sur le trade #%s", t.id)
            _bump(summary, "errors")
    return summary


def _main() -> None:
    import json

    from nyris.core.database import SessionLocal
    from nyris.core.logging import configure_logging

    configure_logging()
    try:
        with cycle_lock(LOCK_PATH):
            with SessionLocal() as db:
                summary = run_cycle(db)
            logger.info("cycle pattern-monitor terminé: %s", summary)
            print(json.dumps(summary, ensure_ascii=False))
    except PatternRunnerBusy:
        logger.warning("un autre cycle pattern-monitor en cours, abandon")
        print('{"status": "busy"}')


if __name__ == "__main__":
    _main()
