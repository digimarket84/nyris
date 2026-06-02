"""Tests de l'export backtest -> strategy_decisions (insertion + idempotence)."""

from decimal import Decimal

from sqlalchemy import select

from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.models.strategy_decision import StrategyDecision
from nyris.strategy.export_decisions import export_asset
from nyris.strategy.models import Candle, StrategyParams

_STEP = 4 * 3600 * 1000
_BASE_T = 9_000_000_000_000  # timestamps de test, hors plage réelle
# params dédiés au test -> params_key unique, isolé des exports réels
P = StrategyParams(timeframe="4h", ema_fast=2, ema_slow=3, ema_trend=5, atr_period=3, max_hold=5)
RUN = "test-export"


def mk(closes):
    out = []
    for idx, c in enumerate(closes):
        cd = Decimal(str(c))
        t = _BASE_T + idx * _STEP
        out.append(
            Candle(open_time=t, close_time=t + _STEP, open=cd, high=cd + 1, low=cd - 1,
                   close=cd, volume=Decimal("1"))
        )
    return out


def _cleanup(db):
    db.query(StrategyDecision).filter(StrategyDecision.params_key == P.key()).delete()
    db.commit()


def test_export_insere_puis_idempotent():
    closes = [100, 100, 100, 100, 100, 99, 98, 101, 106, 112, 119, 127, 136, 130, 120]
    candles = mk(closes)
    with SessionLocal() as db:
        asset = db.scalar(select(Asset).where(Asset.symbol == "BTC"))
        _cleanup(db)
        try:
            r1 = export_asset(db, asset, candles, P, RUN)
            assert r1["inserted"] > 0
            assert r1["skipped"] == 0
            assert r1["evaluated"] == len(closes) - (max(5, 3, 3) + 2)
            # les distributions couvrent toutes les évaluations
            assert sum(r1["actions"].values()) == r1["evaluated"]
            assert sum(r1["reasons"].values()) == r1["evaluated"]

            # rerun : idempotent
            r2 = export_asset(db, asset, candles, P, RUN)
            assert r2["inserted"] == 0
            assert r2["skipped"] == r1["evaluated"]

            # cohérence en base
            rows = db.scalars(
                select(StrategyDecision).where(StrategyDecision.params_key == P.key())
            ).all()
            assert len(rows) == r1["inserted"]
            assert all(x.action in ("enter", "exit", "hold", "skip") for x in rows)
            assert all(x.position_state in ("flat", "open") for x in rows)
            assert all(x.run_id == RUN for x in rows)
        finally:
            _cleanup(db)
