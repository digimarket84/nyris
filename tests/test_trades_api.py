"""Tests d'intégration de l'API (FastAPI TestClient + PostgreSQL)."""

from decimal import Decimal

from fastapi.testclient import TestClient

from nyris.core.database import SessionLocal
from nyris.main import app
from nyris.models.simulated_trade import SimulatedTrade

client = TestClient(app)


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["app"] == "Nyris"


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_list_assets_contient_la_watchlist():
    r = client.get("/api/v1/assets")
    assert r.status_code == 200
    symbols = {a["symbol"] for a in r.json()}
    assert {"BTC", "ETH", "SOL"}.issubset(symbols)


def test_create_trade_validation_montant_invalide():
    r = client.post(
        "/api/v1/trades",
        json={"asset_id": 1, "amount_invested": 0, "entry_price": 100},
    )
    assert r.status_code == 422


def test_flux_creation_puis_fermeture():
    assets = client.get("/api/v1/assets").json()
    btc = next(a for a in assets if a["symbol"] == "BTC")

    create = client.post(
        "/api/v1/trades",
        json={
            "asset_id": btc["id"],
            "amount_invested": "1000",
            "entry_price": "100",
            "entry_fee_rate": "0.001",
        },
    )
    assert create.status_code == 201
    trade = create.json()
    assert trade["status"] == "open"
    assert Decimal(str(trade["quantity"])) == Decimal("9.99")
    assert Decimal(str(trade["entry_fee_amount"])) == Decimal("1.00")
    trade_id = trade["id"]

    close = client.post(
        f"/api/v1/trades/{trade_id}/close",
        json={"exit_price": "150", "exit_fee_rate": "0.001"},
    )
    assert close.status_code == 200
    closed = close.json()
    assert closed["status"] == "closed"
    assert Decimal(str(closed["pnl_net"])) == Decimal("497.00")
    assert Decimal(str(closed["pnl_percent"])) == Decimal("49.70")

    # Fermer un trade déjà fermé -> 409
    again = client.post(
        f"/api/v1/trades/{trade_id}/close",
        json={"exit_price": "150"},
    )
    assert again.status_code == 409

    # Nettoyage
    with SessionLocal() as db:
        obj = db.get(SimulatedTrade, trade_id)
        if obj is not None:
            db.delete(obj)
            db.commit()
