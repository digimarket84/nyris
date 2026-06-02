"""Runner de paper trading automatique (oneshot, déclenché par timer 4h).

Réutilise tout l'existant : candles -> engine.evaluate() (PUR, inchangé) ->
recorder (journal) -> simulated_trades (create/close via pnl). AUCUN ordre réel.

- notional FIXE non-compounding (notional = starting_capital * fraction).
- garde-fous : max_open_positions / max_total_exposure / cooldown / min_notional,
  journalisés avec des reasons normalisées skip_blocked_*.
- idempotence : 1 décision par (asset, tf, bougie, params) + traitement atomique.
- lock fichier léger : empêche deux cycles simultanés.

Exécution : python -m nyris.strategy.runner
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
from nyris.models.simulated_trade import SimulatedTrade, TradeStatus
from nyris.models.strategy_decision import StrategyDecision
from nyris.services import candles as candles_service
from nyris.services import pnl
from nyris.services.binance import BinanceError
from nyris.strategy.backtest import timeframe_hours
from nyris.strategy.engine import evaluate, warmup
from nyris.strategy.models import Action, PositionState, Reason, StrategyParams
from nyris.strategy.recorder import build_decision_record, evaluated_at_from_candle

logger = logging.getLogger("nyris.runner")

UNIVERSE = ["BTC", "ETH", "SOL"]
BASELINE = StrategyParams()  # 4h, EMA 20/50/200, atr2.0, R2.0, hold60
STARTING_CAPITAL = Decimal("1000")
MIN_NOTIONAL = Decimal("10")
CANDLE_LIMIT = 300
LOCK_PATH = "/srv/nyris/runner.lock"


class RunnerBusy(Exception):
    """Un autre cycle runner est déjà en cours."""


@contextmanager
def cycle_lock(path: str = LOCK_PATH):
    fh = open(path, "w")  # noqa: SIM115
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        fh.close()
        raise RunnerBusy() from exc
    try:
        yield
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


# ---- helpers DB (read) ----
def _decision_exists(db: Session, asset_id: int, params: StrategyParams, cct: int) -> bool:
    return db.scalar(
        select(StrategyDecision.id).where(
            StrategyDecision.asset_id == asset_id,
            StrategyDecision.timeframe == params.timeframe,
            StrategyDecision.candle_close_time == cct,
            StrategyDecision.params_key == params.key(),
        )
    ) is not None


def _open_trade(db: Session, asset_id: int) -> SimulatedTrade | None:
    return db.scalar(
        select(SimulatedTrade)
        .where(SimulatedTrade.asset_id == asset_id, SimulatedTrade.status == TradeStatus.open)
        .order_by(SimulatedTrade.id.desc())
    )


def _open_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(SimulatedTrade).where(
                SimulatedTrade.status == TradeStatus.open
            )
        )
        or 0
    )


def _open_exposure(db: Session) -> Decimal:
    return Decimal(
        db.scalar(
            select(func.coalesce(func.sum(SimulatedTrade.amount_invested), 0)).where(
                SimulatedTrade.status == TradeStatus.open
            )
        )
    )


def _last_closed(db: Session, asset_id: int) -> SimulatedTrade | None:
    return db.scalar(
        select(SimulatedTrade)
        .where(SimulatedTrade.asset_id == asset_id, SimulatedTrade.status == TradeStatus.closed)
        .order_by(SimulatedTrade.id.desc())
    )


# ---- helpers métier ----
def _position_state(trade: SimulatedTrade, candles: list, params: StrategyParams) -> PositionState:
    opened_ms = int(trade.opened_at.timestamp() * 1000)
    bars = sum(1 for c in candles if c.close_time > opened_ms)
    stop = trade.stop_price if trade.stop_price is not None else Decimal("0")
    tp = trade.take_profit_price if trade.take_profit_price is not None else Decimal("1e12")
    return PositionState(entry_price=trade.entry_price, stop=stop, take_profit=tp, bars_held=bars)


def _entry_guard(db: Session, asset: Asset, params: StrategyParams, cct: int) -> Reason | None:
    if _open_count(db) >= params.max_open_positions:
        return Reason.skip_blocked_max_positions
    notional = STARTING_CAPITAL * params.position_fraction
    cap = STARTING_CAPITAL * params.max_total_exposure
    if _open_exposure(db) + notional > cap:
        return Reason.skip_blocked_exposure
    last = _last_closed(db, asset.id)
    if last is not None and last.closed_at is not None:
        tf_ms = timeframe_hours(params.timeframe) * 3600 * 1000
        bars_since = (cct - int(last.closed_at.timestamp() * 1000)) / tf_ms
        if bars_since < params.cooldown:
            return Reason.skip_blocked_cooldown
    if notional < MIN_NOTIONAL:
        return Reason.skip_blocked_min_notional
    return None


def _build_trade(asset: Asset, params: StrategyParams, decision, cct: int) -> SimulatedTrade:
    notional = (STARTING_CAPITAL * params.position_fraction).quantize(Decimal("0.01"))
    res = pnl.compute_entry(notional, decision.entry, params.entry_fee_rate)
    return SimulatedTrade(
        asset_id=asset.id,
        status=TradeStatus.open,
        amount_invested=notional,
        entry_price=decision.entry,
        quantity=res.quantity,
        fee_model="flat_rate",
        fee_currency="EUR",
        entry_fee_rate=params.entry_fee_rate,
        entry_fee_amount=res.entry_fee_amount,
        stop_price=decision.stop,
        take_profit_price=decision.take_profit,
        notes="auto:runner",
        opened_at=evaluated_at_from_candle(cct),
    )


def _close_trade(trade: SimulatedTrade, params: StrategyParams, decision, cct: int) -> None:
    res = pnl.compute_close(
        trade.amount_invested, trade.quantity, decision.snapshot.close, params.exit_fee_rate
    )
    trade.exit_price = decision.snapshot.close
    trade.exit_fee_rate = params.exit_fee_rate
    trade.exit_fee_amount = res.exit_fee_amount
    trade.exit_gross_value = res.exit_gross_value
    trade.exit_net_value = res.exit_net_value
    trade.pnl_net = res.pnl_net
    trade.pnl_percent = res.pnl_percent
    trade.status = TradeStatus.closed
    trade.closed_at = evaluated_at_from_candle(cct)


def _bump(summary: dict, key: str) -> None:
    summary[key] = summary.get(key, 0) + 1


def process_asset(
    db: Session, symbol: str, params: StrategyParams, run_id: str, summary: dict
) -> None:
    """Traite UN actif pour la dernière bougie close (atomique, idempotent)."""
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

    trade = _open_trade(db, asset.id)
    position = _position_state(trade, candles, params) if trade is not None else None
    decision = evaluate(candles, position, params)
    pstate = "open" if trade is not None else "flat"

    if decision.action == Action.enter:
        blocked = _entry_guard(db, asset, params, cct)
        if blocked is not None:
            blocked_dec = replace(decision, action=Action.skip, reason=blocked)
            db.add(build_decision_record(asset, params, blocked_dec, pstate, run_id=run_id))
            db.commit()
            _bump(summary, blocked.value)
            return
        new_trade = _build_trade(asset, params, decision, cct)
        db.add(new_trade)
        db.flush()
        db.add(
            build_decision_record(
                asset, params, decision, pstate, run_id=run_id, simulated_trade_id=new_trade.id
            )
        )
        db.commit()
        _bump(summary, "enter")
    elif decision.action == Action.exit and trade is not None:
        _close_trade(trade, params, decision, cct)
        db.flush()
        db.add(
            build_decision_record(
                asset, params, decision, pstate, run_id=run_id, simulated_trade_id=trade.id
            )
        )
        db.commit()
        _bump(summary, "exit")
    else:
        db.add(build_decision_record(asset, params, decision, pstate, run_id=run_id))
        db.commit()
        _bump(summary, "hold_skip")


def run_cycle(
    db: Session, params: StrategyParams | None = None, run_id: str | None = None
) -> dict:
    params = params or BASELINE
    run_id = run_id or f"live-{params.key()}"
    summary: dict = {"run_id": run_id}
    for symbol in UNIVERSE:
        try:
            process_asset(db, symbol, params, run_id, summary)
        except Exception:
            db.rollback()
            logger.exception("erreur lors du traitement de %s", symbol)
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
            logger.info("cycle terminé: %s", summary)
            print(json.dumps(summary, ensure_ascii=False))
    except RunnerBusy:
        logger.warning("un autre cycle runner est en cours, abandon")
        print('{"status": "busy"}')


if __name__ == "__main__":
    _main()
