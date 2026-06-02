"""Tests de l'endpoint de relecture GET /api/v1/strategy/decisions."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from nyris.core.database import SessionLocal
from nyris.main import app
from nyris.models.asset import Asset
from nyris.models.strategy_decision import StrategyDecision

client = TestClient(app)

RUN = "test-api-run"
PK = "test-api"
_BASE = datetime(2024, 1, 1, tzinfo=UTC)
_ROWS = [
    ("hold", "hold_no_trend", "flat"),
    ("enter", "enter_signal", "flat"),
    ("hold", "hold_in_position", "open"),
]


def _seed(db, asset):
    rows = []
    for k, (action, reason, ps) in enumerate(_ROWS):
        dt = _BASE + timedelta(hours=4 * k)
        cct = int(dt.timestamp() * 1000)
        rows.append(
            StrategyDecision(
                evaluated_at=dt,
                asset_id=asset.id,
                symbol="BTC",
                timeframe="4h",
                candle_close_time=cct,
                close_price=Decimal("100"),
                action=action,
                reason=reason,
                position_state=ps,
                params_key=PK,
                run_id=RUN,
            )
        )
    db.add_all(rows)
    db.commit()


def _cleanup(db):
    db.query(StrategyDecision).filter_by(run_id=RUN).delete()
    db.commit()


def test_decisions_endpoint_filtres_pagination_tri():
    with SessionLocal() as db:
        asset = db.scalar(select(Asset).where(Asset.symbol == "BTC"))
        _cleanup(db)
        _seed(db, asset)
    try:
        # base : enveloppe + total + tri desc par evaluated_at
        r = client.get(f"/api/v1/strategy/decisions?run_id={RUN}")
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"items", "total", "limit", "offset"}
        assert body["total"] == 3 and len(body["items"]) == 3
        ts = [it["evaluated_at"] for it in body["items"]]
        assert ts == sorted(ts, reverse=True)  # tri par défaut

        # filtre action
        r2 = client.get(f"/api/v1/strategy/decisions?run_id={RUN}&action=hold").json()
        assert r2["total"] == 2 and all(i["action"] == "hold" for i in r2["items"])

        # filtre position_state
        r3 = client.get(f"/api/v1/strategy/decisions?run_id={RUN}&position_state=open").json()
        assert r3["total"] == 1 and r3["items"][0]["reason"] == "hold_in_position"

        # filtre temporel (evaluated_at >= 05:00 -> seule la 3e ligne 08:00)
        r4 = client.get(
            f"/api/v1/strategy/decisions?run_id={RUN}&from=2024-01-01T05:00:00Z"
        ).json()
        assert r4["total"] == 1

        # pagination
        r5 = client.get(f"/api/v1/strategy/decisions?run_id={RUN}&limit=1&offset=0").json()
        assert r5["total"] == 3 and len(r5["items"]) == 1 and r5["limit"] == 1

        # date naïve -> 422
        r6 = client.get("/api/v1/strategy/decisions?from=2024-01-01T00:00:00")
        assert r6.status_code == 422
    finally:
        with SessionLocal() as db:
            _cleanup(db)
