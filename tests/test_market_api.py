"""Tests d'intégration de l'intégration Binance (transport mocké)."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from nyris.core.database import SessionLocal
from nyris.main import app
from nyris.models.asset import Asset
from nyris.services import binance, market
from nyris.services.binance import BinanceUnavailable

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_cache():
    market.clear_cache()
    yield
    market.clear_cache()


def _asset_id(symbol: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(Asset).where(Asset.symbol == symbol)).id


def _set_binance_symbol(symbol: str, binance_symbol: str | None) -> None:
    with SessionLocal() as db:
        asset = db.scalar(select(Asset).where(Asset.symbol == symbol))
        asset.binance_symbol = binance_symbol
        db.commit()


def test_sync_met_a_jour_les_metadonnees(monkeypatch):
    fake_info = {
        "BTCEUR": {"status": "TRADING", "baseAsset": "BTC", "quoteAsset": "EUR"},
        "ETHEUR": {"status": "TRADING", "baseAsset": "ETH", "quoteAsset": "EUR"},
        "SOLEUR": {"status": "TRADING", "baseAsset": "SOL", "quoteAsset": "EUR"},
    }
    monkeypatch.setattr(binance, "get_exchange_info", lambda: fake_info)
    r = client.post("/api/v1/market/sync")
    assert r.status_code == 200
    body = r.json()
    assert body["checked"] >= 7
    by_symbol = {d["symbol"]: d for d in body["assets"]}
    assert by_symbol["BTC"]["binance_symbol"] == "BTCEUR"
    assert by_symbol["BTC"]["binance_status"] == "TRADING"
    assert by_symbol["ATH"]["binance_symbol"] is None  # pas de paire EUR

    # is_tradeable NON modifié par le sync (ATH reste watch_only non tradable)
    assets = client.get("/api/v1/assets").json()
    ath = next(a for a in assets if a["symbol"] == "ATH")
    assert ath["is_tradeable"] is False


def test_price_ok(monkeypatch):
    _set_binance_symbol("BTC", "BTCEUR")
    monkeypatch.setattr(binance, "get_price", lambda s: Decimal("57321.40"))
    r = client.get(f"/api/v1/market/price?asset_id={_asset_id('BTC')}")
    assert r.status_code == 200
    body = r.json()
    assert body["binance_symbol"] == "BTCEUR"
    assert body["quote_currency"] == "EUR"
    assert Decimal(str(body["price"])) == Decimal("57321.40")


def test_price_sans_paire_eur_409():
    _set_binance_symbol("ATH", None)
    r = client.get(f"/api/v1/market/price?asset_id={_asset_id('ATH')}")
    assert r.status_code == 409


def test_price_asset_inconnu_404():
    r = client.get("/api/v1/market/price?asset_id=99999999")
    assert r.status_code == 404


def test_price_binance_indispo_503(monkeypatch):
    _set_binance_symbol("BTC", "BTCEUR")

    def boom(symbol):
        raise BinanceUnavailable("indisponible")

    monkeypatch.setattr(binance, "get_price", boom)
    r = client.get(f"/api/v1/market/price?asset_id={_asset_id('BTC')}")
    assert r.status_code == 503


def test_prices_batch(monkeypatch):
    _set_binance_symbol("BTC", "BTCEUR")
    _set_binance_symbol("ETH", "ETHEUR")
    monkeypatch.setattr(
        binance,
        "get_all_prices",
        lambda: {"BTCEUR": Decimal("57000.00"), "ETHEUR": Decimal("3000.00")},
    )
    r = client.get("/api/v1/market/prices")
    assert r.status_code == 200
    body = r.json()
    symbols = {p["binance_symbol"] for p in body["prices"]}
    assert {"BTCEUR", "ETHEUR"}.issubset(symbols)
    assert body["quote_currency"] == "EUR"
