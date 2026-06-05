"""Tests du gardien temps réel SHORT : stop/TP au niveau exact (1m), fermeture gardée.

On teste process_trade sur UN trade inséré (jamais run_cycle), pour ne pas toucher
les positions réelles ouvertes en base.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.models.short_trade import ShortTrade
from nyris.strategy.models import Candle
from nyris.strategy.short_monitor import process_trade

BASE_T = 9_300_000_000_000
RUN = "test-monitor"


def candle(o, h, lo, c):
    return Candle(BASE_T, BASE_T + 60_000, Decimal(str(o)), Decimal(str(h)),
                  Decimal(str(lo)), Decimal(str(c)), Decimal("1"))


def _insert(db, asset_id, status="open"):
    t = ShortTrade(
        asset_id=asset_id, status=status, side="short", amount_invested=Decimal("25.00"),
        entry_price=Decimal("100"), quantity=Decimal("0.25"),
        stop_price=Decimal("105"), take_profit_price=Decimal("90"),
        commission_rate=Decimal("0.001"), spread_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"), funding_rate_daily=Decimal("0.0003"),
        entry_cost=Decimal("0.05"), run_id=RUN, params_key="test",
        opened_at=datetime.fromtimestamp(BASE_T / 1000, tz=UTC),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _cleanup(db):
    db.query(ShortTrade).filter(ShortTrade.run_id == RUN).delete()
    db.commit()


def _btc_id(db):
    return db.scalar(select(Asset.id).where(Asset.symbol == "BTC"))


def test_exact_stop(monkeypatch):
    monkeypatch.setattr("nyris.services.candles.get_candles",
                        lambda *a, **k: [candle(104.5, 106, 104, 104.5)])  # high 106 >= stop 105
    with SessionLocal() as db:
        _cleanup(db)
        t = _insert(db, _btc_id(db))
        try:
            s = {}
            process_trade(db, t, "BTCEUR", s)
            assert s.get("exit_stop") == 1
            r = db.get(ShortTrade, t.id)
            assert r.status == "closed" and r.exit_reason == "exit_short_stop"
            assert r.exit_price == Decimal("105")  # niveau EXACT, pas la clôture 104.5
        finally:
            _cleanup(db)


def test_exact_take_profit(monkeypatch):
    monkeypatch.setattr("nyris.services.candles.get_candles",
                        lambda *a, **k: [candle(90.5, 92, 89, 90.5)])  # low 89 <= tp 90
    with SessionLocal() as db:
        _cleanup(db)
        t = _insert(db, _btc_id(db))
        try:
            s = {}
            process_trade(db, t, "BTCEUR", s)
            assert s.get("exit_tp") == 1
            r = db.get(ShortTrade, t.id)
            assert r.status == "closed" and r.exit_reason == "exit_short_take_profit"
            assert r.exit_price == Decimal("90")  # niveau EXACT, pas la clôture 90.5
            assert r.pnl_gross > 0  # rachat à 90 < vente à 100 -> gain brut
        finally:
            _cleanup(db)


def test_no_exit_in_range(monkeypatch):
    monkeypatch.setattr("nyris.services.candles.get_candles",
                        lambda *a, **k: [candle(100, 102, 98, 100)])  # entre tp 90 et stop 105
    with SessionLocal() as db:
        _cleanup(db)
        t = _insert(db, _btc_id(db))
        try:
            s = {}
            process_trade(db, t, "BTCEUR", s)
            assert s.get("watch") == 1
            assert db.get(ShortTrade, t.id).status == "open"  # toujours ouvert
        finally:
            _cleanup(db)


def test_guarded_when_already_closed(monkeypatch):
    monkeypatch.setattr("nyris.services.candles.get_candles",
                        lambda *a, **k: [candle(104.5, 106, 104, 104.5)])  # stop touché
    with SessionLocal() as db:
        _cleanup(db)
        t = _insert(db, _btc_id(db), status="closed")  # déjà fermé
        try:
            s = {}
            process_trade(db, t, "BTCEUR", s)
            assert s.get("already_closed") == 1  # fermeture gardée -> rowcount 0
        finally:
            _cleanup(db)
