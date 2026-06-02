"""Tests d'intégration de l'endpoint d'agrégation du portefeuille."""

from decimal import Decimal

from fastapi.testclient import TestClient

from nyris.core.database import SessionLocal
from nyris.main import app
from nyris.models.simulated_trade import SimulatedTrade

client = TestClient(app)

_EXPECTED_KEYS = {
    "currency",
    "counts",
    "realized",
    "open_exposure",
    "by_asset",
    "best_asset",
    "worst_asset",
}


def _create_closed(asset_id: int, invested: str, entry: str, exit_price: str) -> int:
    created = client.post(
        "/api/v1/trades",
        json={
            "asset_id": asset_id,
            "amount_invested": invested,
            "entry_price": entry,
            "entry_fee_rate": "0",
        },
    )
    assert created.status_code == 201
    trade_id = created.json()["id"]
    closed = client.post(
        f"/api/v1/trades/{trade_id}/close",
        json={"exit_price": exit_price, "exit_fee_rate": "0"},
    )
    assert closed.status_code == 200
    return trade_id


def test_portfolio_summary_structure():
    r = client.get("/api/v1/portfolio/summary")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= _EXPECTED_KEYS
    assert body["currency"] == "EUR"


def test_portfolio_summary_agregation_par_delta():
    assets = client.get("/api/v1/assets").json()
    btc = next(a for a in assets if a["symbol"] == "BTC")
    eth = next(a for a in assets if a["symbol"] == "ETH")

    base = client.get("/api/v1/portfolio/summary").json()
    base_closed = base["counts"]["closed"]
    base_pnl = Decimal(str(base["realized"]["pnl_net"]))

    # BTC : 1000 @100 -> 150  => PnL +500 (sans frais)
    t1 = _create_closed(btc["id"], "1000", "100", "150")
    # ETH : 1000 @100 -> 80   => PnL -200 (sans frais)
    t2 = _create_closed(eth["id"], "1000", "100", "80")

    s = client.get("/api/v1/portfolio/summary").json()
    assert s["counts"]["closed"] == base_closed + 2
    assert Decimal(str(s["realized"]["pnl_net"])) == base_pnl + Decimal("300.00")

    by_symbol = {a["symbol"] for a in s["by_asset"]}
    assert {"BTC", "ETH"}.issubset(by_symbol)

    assert s["best_asset"] is not None
    assert s["worst_asset"] is not None
    assert Decimal(str(s["best_asset"]["pnl_net"])) >= Decimal(str(s["worst_asset"]["pnl_net"]))

    # Nettoyage
    with SessionLocal() as db:
        for trade_id in (t1, t2):
            obj = db.get(SimulatedTrade, trade_id)
            if obj is not None:
                db.delete(obj)
        db.commit()
