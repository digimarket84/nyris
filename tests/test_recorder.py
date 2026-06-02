"""Tests de la couche recorder (mapping pur + idempotence + filtres)."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select

from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.models.strategy_decision import StrategyDecision
from nyris.strategy.models import Action, Decision, Reason, Snapshot, StrategyParams
from nyris.strategy.recorder import build_decision_record, record_decision

_CCT = 1234567890000  # bougie de test improbable


def _snap(cct=_CCT):
    return Snapshot(
        candle_close_time=cct,
        close=Decimal("100"),
        ema_fast=Decimal("99"),
        ema_slow=Decimal("98"),
        ema_trend=Decimal("95"),
        atr=Decimal("2"),
    )


def test_params_key():
    k = StrategyParams().key()
    assert k == "t4h_et200_20/50_atr2.0_R2.0_h60"


def test_build_decision_record_mapping():
    asset = SimpleNamespace(id=1, symbol="BTC")
    params = StrategyParams()
    dec = Decision(
        Action.enter, Reason.enter_signal, _snap(),
        entry=Decimal("100"), stop=Decimal("97"), take_profit=Decimal("106"),
    )
    rec = build_decision_record(asset, params, dec, "flat", run_id="r1")
    assert rec.asset_id == 1 and rec.symbol == "BTC"
    assert rec.action == "enter" and rec.reason == "enter_signal"
    assert rec.position_state == "flat"
    assert rec.close_price == Decimal("100")
    assert rec.stop_price == Decimal("97") and rec.take_profit_price == Decimal("106")
    assert rec.params_key == params.key()
    assert rec.run_id == "r1"
    assert rec.candle_close_time == _CCT
    # evaluated_at dérivé de la bougie (pas de l'horloge système)
    assert rec.evaluated_at == datetime.fromtimestamp(_CCT / 1000, tz=UTC)


def test_record_decision_idempotent_et_filtre():
    params = StrategyParams()
    dec = Decision(Action.hold, Reason.hold_no_trend, _snap())
    with SessionLocal() as db:
        asset = db.scalar(select(Asset).where(Asset.symbol == "BTC"))
        db.query(StrategyDecision).filter_by(
            candle_close_time=_CCT, params_key=params.key()
        ).delete()
        db.commit()
        try:
            r1 = record_decision(db, asset, params, dec, "flat")
            r2 = record_decision(db, asset, params, dec, "flat")
            assert r1.id == r2.id  # idempotent, pas de doublon

            rows = db.scalars(
                select(StrategyDecision).where(
                    StrategyDecision.candle_close_time == _CCT,
                    StrategyDecision.params_key == params.key(),
                )
            ).all()
            assert len(rows) == 1
            assert rows[0].action == "hold" and rows[0].reason == "hold_no_trend"
            assert rows[0].position_state == "flat"
        finally:
            db.query(StrategyDecision).filter_by(
                candle_close_time=_CCT, params_key=params.key()
            ).delete()
            db.commit()
