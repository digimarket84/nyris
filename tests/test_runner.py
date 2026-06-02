"""Tests du runner paper-auto. Intégration : suppose une base de dev (pas de trades live)."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.models.simulated_trade import SimulatedTrade, TradeStatus
from nyris.models.strategy_decision import StrategyDecision
from nyris.strategy.indicators import ema
from nyris.strategy.models import Candle, Reason, StrategyParams
from nyris.strategy.runner import (
    RunnerBusy,
    _entry_guard,
    _position_state,
    cycle_lock,
    process_asset,
)

STEP = 4 * 3600 * 1000
BASE_T = 9_100_000_000_000
RUN = "test-runner"
P = StrategyParams(
    ema_fast=2, ema_slow=3, ema_trend=5, atr_period=3, max_hold=5, cooldown=3,
    max_open_positions=3, max_total_exposure=Decimal("0.50"), position_fraction=Decimal("0.10"),
)


def mk(closes):
    out = []
    for i, c in enumerate(closes):
        cd = Decimal(str(c))
        t = BASE_T + i * STEP
        out.append(Candle(open_time=t, close_time=t + STEP, open=cd, high=cd + 1, low=cd - 1,
                          close=cd, volume=Decimal("1")))
    return out


def enter_candles():
    closes = [100, 100, 100, 100, 100, 99, 98, 101, 106, 112, 119, 127, 136]
    cl = [float(x) for x in closes]
    ef, es, et = ema(cl, 2), ema(cl, 3), ema(cl, 5)
    idx = None
    for i in range(7, len(cl)):
        if None in (ef[i], es[i], et[i], ef[i - 1], es[i - 1]):
            continue
        if ef[i - 1] <= es[i - 1] and ef[i] > es[i] and cl[i] > et[i]:
            idx = i
            break
    assert idx is not None
    return mk(closes[: idx + 1])


def _btc(db):
    a = db.scalar(select(Asset).where(Asset.symbol == "BTC"))
    if not a.binance_symbol:
        a.binance_symbol = "BTCEUR"
        a.is_tradeable = True
        db.commit()
    return a


def _cleanup(db):
    decs = db.scalars(select(StrategyDecision).where(StrategyDecision.run_id == RUN)).all()
    tids = [d.simulated_trade_id for d in decs if d.simulated_trade_id]
    db.query(StrategyDecision).filter(StrategyDecision.run_id == RUN).delete()
    db.query(StrategyDecision).filter(StrategyDecision.params_key == P.key()).delete()
    for tid in tids:
        obj = db.get(SimulatedTrade, tid)
        if obj:
            db.delete(obj)
    db.query(SimulatedTrade).filter(SimulatedTrade.notes == "test-runner-manual").delete()
    db.commit()


def _insert_open(db, asset_id, stop, tp, opened_ms):
    t = SimulatedTrade(
        asset_id=asset_id, status=TradeStatus.open, amount_invested=Decimal("100.00"),
        entry_price=Decimal("100"), quantity=Decimal("1"), fee_model="flat_rate",
        fee_currency="EUR", entry_fee_rate=Decimal("0.001"), entry_fee_amount=Decimal("0.10"),
        stop_price=stop, take_profit_price=tp, notes="test-runner-manual",
        opened_at=datetime.fromtimestamp(opened_ms / 1000, tz=UTC),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def test_cycle_lock_busy(tmp_path):
    p = str(tmp_path / "lock")
    with cycle_lock(p):
        with pytest.raises(RunnerBusy):
            with cycle_lock(p):
                pass


def test_position_state_bars_et_niveaux():
    candles = mk([100] * 10)
    opened_ms = candles[2].close_time
    trade = SimpleNamespace(
        opened_at=datetime.fromtimestamp(opened_ms / 1000, tz=UTC),
        stop_price=Decimal("90"), take_profit_price=Decimal("120"), entry_price=Decimal("100"),
    )
    ps = _position_state(trade, candles, P)
    assert ps.bars_held == 7  # indices 3..9
    assert ps.stop == Decimal("90") and ps.take_profit == Decimal("120")


def test_entry_guard_max_positions():
    with SessionLocal() as db:
        asset = _btc(db)
        r = _entry_guard(db, asset, StrategyParams(max_open_positions=0), BASE_T)
        assert r == Reason.skip_blocked_max_positions


def test_entry_guard_exposure():
    with SessionLocal() as db:
        asset = _btc(db)
        pg = StrategyParams(max_open_positions=999, max_total_exposure=Decimal("0"))
        assert _entry_guard(db, asset, pg, BASE_T) == Reason.skip_blocked_exposure


def test_process_asset_fail_safe(monkeypatch):
    monkeypatch.setattr("nyris.services.candles.get_candles", lambda *a, **k: mk([100, 100, 100]))
    with SessionLocal() as db:
        _btc(db)
        s = {}
        process_asset(db, "BTC", P, RUN, s)
        assert s.get("fail_safe") == 1


def test_process_asset_enter_then_idempotent(monkeypatch):
    candles = enter_candles()
    monkeypatch.setattr("nyris.services.candles.get_candles", lambda *a, **k: candles)
    with SessionLocal() as db:
        asset = _btc(db)
        # isolation (base de dev) : aucune position BTC ouverte
        db.query(SimulatedTrade).filter(
            SimulatedTrade.asset_id == asset.id, SimulatedTrade.status == TradeStatus.open
        ).delete()
        db.commit()
        _cleanup(db)
        try:
            s = {}
            process_asset(db, "BTC", P, RUN, s)
            assert s.get("enter") == 1
            tr = db.scalar(
                select(SimulatedTrade).where(
                    SimulatedTrade.asset_id == asset.id, SimulatedTrade.status == TradeStatus.open
                )
            )
            assert tr is not None
            assert tr.amount_invested == Decimal("100.00")  # 1000 * 0.10 (non-compounding)
            assert tr.stop_price is not None and tr.take_profit_price is not None
            dec = db.scalar(
                select(StrategyDecision).where(
                    StrategyDecision.run_id == RUN, StrategyDecision.action == "enter"
                )
            )
            assert dec is not None and dec.simulated_trade_id == tr.id
            assert dec.reason == "enter_signal"

            # rerun même bougie -> idempotent, pas de second trade
            s2 = {}
            process_asset(db, "BTC", P, RUN, s2)
            assert s2.get("already_processed") == 1
            n_open = len(
                db.scalars(
                    select(SimulatedTrade).where(
                        SimulatedTrade.asset_id == asset.id,
                        SimulatedTrade.status == TradeStatus.open,
                    )
                ).all()
            )
            assert n_open == 1
        finally:
            _cleanup(db)


def test_process_asset_exit(monkeypatch):
    candles = mk([100] * 12)
    monkeypatch.setattr("nyris.services.candles.get_candles", lambda *a, **k: candles)
    with SessionLocal() as db:
        asset = _btc(db)
        db.query(SimulatedTrade).filter(
            SimulatedTrade.asset_id == asset.id, SimulatedTrade.status == TradeStatus.open
        ).delete()
        db.commit()
        _cleanup(db)
        try:
            tr = _insert_open(db, asset.id, Decimal("105"), Decimal("200"), candles[0].close_time)
            s = {}
            process_asset(db, "BTC", P, RUN, s)
            assert s.get("exit") == 1
            db.refresh(tr)
            assert tr.status == TradeStatus.closed
            assert tr.pnl_net is not None and tr.exit_price == Decimal("100")
            dec = db.scalar(
                select(StrategyDecision).where(
                    StrategyDecision.run_id == RUN, StrategyDecision.action == "exit"
                )
            )
            assert dec is not None and dec.simulated_trade_id == tr.id
            assert dec.reason == "exit_stop"
        finally:
            _cleanup(db)
