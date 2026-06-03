"""Tests du runner SHORT : non-collision baseline, entrée/idempotence, sortie, garde-fou, lock."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.models.short_trade import ShortTrade
from nyris.models.strategy_decision import StrategyDecision
from nyris.strategy import runner as baseline  # import lecture seule pour la preuve d'isolation
from nyris.strategy.indicators import ema
from nyris.strategy.models import Candle
from nyris.strategy.short_models import ShortParams
from nyris.strategy.short_runner import (
    ShortRunnerBusy,
    _open_count,
    cycle_lock,
    process_asset,
)

STEP = 4 * 3600 * 1000
BASE_T = 9_200_000_000_000
P = ShortParams(ema_trend=5, ema_pullback=3, atr_period=3, max_hold=5, run_id="test-short")


def mk(closes):
    out = []
    for i, c in enumerate(closes):
        cd = Decimal(str(c))
        t = BASE_T + STEP * i
        out.append(
            Candle(
                open_time=t,
                close_time=t + STEP,
                open=cd,
                high=cd + 1,
                low=cd - 1,
                close=cd,
                volume=Decimal("1"),
            )
        )
    return out


def enter_candles():
    closes = [120, 118, 116, 114, 112, 110, 108, 106, 104, 102, 100]
    ep = ema([float(x) for x in closes], P.ema_pullback)
    candles = mk(closes)
    i = len(closes) - 1
    candles[-1] = replace(
        candles[-1], high=Decimal(str(ep[i] + 5)), open=candles[-1].close + Decimal("3")
    )
    return candles


def _btc(db):
    a = db.scalar(select(Asset).where(Asset.symbol == "BTC"))
    if not a.binance_symbol:
        a.binance_symbol = "BTCEUR"
        a.is_tradeable = True
        db.commit()
    return a


def _cleanup(db):
    db.query(StrategyDecision).filter(StrategyDecision.run_id == P.run_id).delete()
    db.query(StrategyDecision).filter(StrategyDecision.params_key == P.key()).delete()
    db.query(ShortTrade).filter(ShortTrade.run_id == P.run_id).delete()
    db.commit()


def _insert_open_short(db, asset_id, stop, tp, opened_ms):
    t = ShortTrade(
        asset_id=asset_id,
        status="open",
        side="short",
        amount_invested=Decimal("25.00"),
        entry_price=Decimal("100"),
        quantity=Decimal("0.25"),
        stop_price=stop,
        take_profit_price=tp,
        commission_rate=Decimal("0.001"),
        spread_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"),
        funding_rate_daily=Decimal("0.0003"),
        entry_cost=Decimal("0.05"),
        run_id=P.run_id,
        params_key=P.key(),
        notes="test-short",
        opened_at=datetime.fromtimestamp(opened_ms / 1000, tz=UTC),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def test_lock_busy(tmp_path):
    p = str(tmp_path / "lock")
    with cycle_lock(p):
        with pytest.raises(ShortRunnerBusy):
            with cycle_lock(p):
                pass


def test_non_collision_avec_baseline():
    """Un short ouvert ne doit JAMAIS apparaître dans les requêtes du baseline."""
    with SessionLocal() as db:
        asset = _btc(db)
        _cleanup(db)
        try:
            before_count = baseline._open_count(db)
            before_trade = baseline._open_trade(db, asset.id)
            _insert_open_short(db, asset.id, Decimal("105"), Decimal("90"), BASE_T)
            # baseline (lit simulated_trades) : inchangé
            assert baseline._open_count(db) == before_count
            assert baseline._open_trade(db, asset.id) is before_trade or (
                before_trade is None and baseline._open_trade(db, asset.id) is None
            )
            # côté short : visible
            assert _open_count(db) >= 1
        finally:
            _cleanup(db)


def test_enter_short_then_idempotent(monkeypatch):
    candles = enter_candles()
    monkeypatch.setattr("nyris.services.candles.get_candles", lambda *a, **k: candles)
    with SessionLocal() as db:
        asset = _btc(db)
        db.query(ShortTrade).filter(
            ShortTrade.asset_id == asset.id, ShortTrade.status == "open"
        ).delete()
        db.commit()
        _cleanup(db)
        try:
            s = {}
            process_asset(db, "BTC", P, s)
            assert s.get("enter") == 1
            tr = db.scalar(
                select(ShortTrade).where(
                    ShortTrade.asset_id == asset.id, ShortTrade.status == "open"
                )
            )
            assert tr is not None and tr.side == "short"
            assert tr.amount_invested == Decimal("25.00")  # 50 * 0.5
            assert tr.stop_price > tr.entry_price > tr.take_profit_price
            dec = db.scalar(
                select(StrategyDecision).where(
                    StrategyDecision.run_id == P.run_id, StrategyDecision.action == "enter"
                )
            )
            assert dec is not None
            assert dec.simulated_trade_id is None  # FK -> simulated_trades : non utilisé
            assert dec.notes == f"short_trade:{tr.id}"
            # rerun -> idempotent
            s2 = {}
            process_asset(db, "BTC", P, s2)
            assert s2.get("already_processed") == 1
        finally:
            _cleanup(db)


def test_exit_short(monkeypatch):
    candles = mk([100] * 12)
    monkeypatch.setattr("nyris.services.candles.get_candles", lambda *a, **k: candles)
    with SessionLocal() as db:
        asset = _btc(db)
        db.query(ShortTrade).filter(
            ShortTrade.asset_id == asset.id, ShortTrade.status == "open"
        ).delete()
        db.commit()
        _cleanup(db)
        try:
            tr = _insert_open_short(
                db, asset.id, Decimal("95"), Decimal("10"), candles[0].close_time
            )
            s = {}
            process_asset(db, "BTC", P, s)
            assert s.get("exit") == 1
            db.refresh(tr)
            assert tr.status == "closed" and tr.pnl_net is not None
            assert tr.exit_price == Decimal("100")
        finally:
            _cleanup(db)


def test_guard_max_positions(monkeypatch):
    candles = enter_candles()
    monkeypatch.setattr("nyris.services.candles.get_candles", lambda *a, **k: candles)
    pg = replace(P, max_open_positions=1)
    with SessionLocal() as db:
        eth = db.scalar(select(Asset).where(Asset.symbol == "ETH"))
        btc = _btc(db)
        db.query(ShortTrade).filter(ShortTrade.status == "open").delete()  # isolation test
        db.commit()
        _cleanup(db)
        try:
            _insert_open_short(
                db, eth.id, Decimal("105"), Decimal("90"), BASE_T
            )  # 1 short déjà ouvert
            s = {}
            process_asset(db, "BTC", pg, s)  # tente d'ouvrir un 2e -> bloqué
            assert s.get("skip_blocked_max_positions") == 1
            assert (
                db.scalar(
                    select(ShortTrade).where(
                        ShortTrade.asset_id == btc.id, ShortTrade.status == "open"
                    )
                )
                is None
            )
        finally:
            db.query(ShortTrade).filter(ShortTrade.params_key == pg.key()).delete()
            _cleanup(db)
