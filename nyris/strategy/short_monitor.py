"""Gardien de position SHORT en quasi temps réel (oneshot, 1m).

NE PREND AUCUN TRADE. Il surveille les positions `short_trades` ouvertes (tous run_id)
chaque minute sur les bougies 1m et déclenche stop / take-profit au NIVEAU EXACT
(via le high/low intra-bougie) — au lieu d'attendre la clôture du timeframe d'entrée
(15m) et de sortir au prix de clôture.

Synergie : v5 (entrée 15m) pose et fait trailing du `stop_price` ; ce moniteur
l'applique vite et précisément en 1m. Fermeture idempotente et gardée
(UPDATE ... WHERE status='open') pour être sûr face au runner d'entrée.

Isolation : lock dédié, ne touche jamais `simulated_trades`, n'importe ni ne modifie
le baseline. N'écrit PAS dans `strategy_decisions` (pas de collision d'idempotence).

Exécution : python -m nyris.strategy.short_monitor
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from nyris.models.asset import Asset
from nyris.models.short_trade import ShortTrade
from nyris.services import candles as candles_service
from nyris.services.binance import BinanceError
from nyris.strategy import short_pnl
from nyris.strategy.recorder import evaluated_at_from_candle
from nyris.strategy.short_runner import ShortRunnerBusy, cycle_lock

logger = logging.getLogger("nyris.short_monitor")

LOCK_PATH = "/srv/nyris/short-monitor.lock"
MONITOR_TF = "1m"
CANDLE_LIMIT = 5


def _bump(summary: dict, key: str) -> None:
    summary[key] = summary.get(key, 0) + 1


def _rates(trade: ShortTrade) -> SimpleNamespace:
    """Vue des taux de coûts FIGÉS du trade (pour un PnL fidèle à l'entrée)."""
    return SimpleNamespace(
        commission_rate=trade.commission_rate,
        spread_rate=trade.spread_rate,
        slippage_rate=trade.slippage_rate,
        funding_rate_daily=trade.funding_rate_daily,
    )


def _close_exact(db: Session, trade: ShortTrade, exit_price, reason: str, cct_ms: int) -> bool:
    """Ferme au niveau EXACT, de façon gardée (uniquement si encore 'open')."""
    opened_ms = int(trade.opened_at.timestamp() * 1000)
    hours = max((cct_ms - opened_ms) / 3_600_000, 0.0)
    res = short_pnl.compute_short_close(
        trade.amount_invested, trade.quantity, trade.entry_cost, exit_price,
        _rates(trade), bars_held=hours, tf_hours=1.0,
    )
    r = db.execute(
        update(ShortTrade)
        .where(ShortTrade.id == trade.id, ShortTrade.status == "open")
        .values(
            status="closed", exit_price=exit_price, exit_cost=res.exit_cost,
            funding_cost=res.funding_cost, pnl_gross=res.pnl_gross, pnl_net=res.pnl_net,
            pnl_percent=res.pnl_percent, exit_reason=reason,
            closed_at=evaluated_at_from_candle(cct_ms),
            notes=(trade.notes or "") + ";monitor:exact",
        )
    )
    db.commit()
    return r.rowcount == 1


def process_trade(
    db: Session, trade: ShortTrade, binance_symbol: str | None, summary: dict
) -> None:
    if not binance_symbol:
        _bump(summary, "ineligible")
        return
    try:
        candles = candles_service.get_candles(binance_symbol, MONITOR_TF, CANDLE_LIMIT)
    except BinanceError as exc:
        logger.warning("monitor %s: données indisponibles (%s)", binance_symbol, exc)
        _bump(summary, "data_error")
        return
    if not candles:
        _bump(summary, "no_data")
        return

    last = candles[-1]
    cct = last.close_time
    hi, lo = float(last.high), float(last.low)
    stop = float(trade.stop_price) if trade.stop_price is not None else None
    tp = float(trade.take_profit_price) if trade.take_profit_price is not None else None

    # priorité au stop (risque d'abord) si la même bougie touche les deux
    if stop is not None and hi >= stop:
        if _close_exact(db, trade, trade.stop_price, "exit_short_stop", cct):
            _bump(summary, "exit_stop")
        else:
            _bump(summary, "already_closed")
    elif tp is not None and lo <= tp:
        if _close_exact(db, trade, trade.take_profit_price, "exit_short_take_profit", cct):
            _bump(summary, "exit_tp")
        else:
            _bump(summary, "already_closed")
    else:
        _bump(summary, "watch")


def run_cycle(db: Session) -> dict:
    summary: dict = {"runner": "short-monitor"}
    opens = db.execute(
        select(ShortTrade, Asset.binance_symbol)
        .join(Asset, ShortTrade.asset_id == Asset.id)
        .where(ShortTrade.status == "open")
    ).all()
    for trade, bsym in opens:
        try:
            process_trade(db, trade, bsym, summary)
        except Exception:
            db.rollback()
            logger.exception("erreur monitor sur le trade #%s", trade.id)
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
            logger.info("cycle monitor terminé: %s", summary)
            print(json.dumps(summary, ensure_ascii=False))
    except ShortRunnerBusy:
        logger.warning("un autre cycle monitor est en cours, abandon")
        print('{"status": "busy"}')


if __name__ == "__main__":
    _main()
