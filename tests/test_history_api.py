"""Tests d'intégration : historique filtrable/paginé + agrégation filtrée."""

from decimal import Decimal

from fastapi.testclient import TestClient

from nyris.core.database import SessionLocal
from nyris.main import app
from nyris.models.simulated_trade import SimulatedTrade

client = TestClient(app)


def _btc_eth_ids() -> tuple[int, int]:
    assets = client.get("/api/v1/assets").json()
    btc = next(a for a in assets if a["symbol"] == "BTC")
    eth = next(a for a in assets if a["symbol"] == "ETH")
    return btc["id"], eth["id"]


def _open_trade(asset_id: int, invested="1000", entry="100") -> int:
    r = client.post(
        "/api/v1/trades",
        json={
            "asset_id": asset_id,
            "amount_invested": invested,
            "entry_price": entry,
            "entry_fee_rate": "0",
        },
    )
    assert r.status_code == 201
    return r.json()["id"]


def _close(trade_id: int, exit_price="150") -> None:
    r = client.post(
        f"/api/v1/trades/{trade_id}/close",
        json={"exit_price": exit_price, "exit_fee_rate": "0"},
    )
    assert r.status_code == 200


def _cleanup(ids: list[int]) -> None:
    with SessionLocal() as db:
        for tid in ids:
            obj = db.get(SimulatedTrade, tid)
            if obj is not None:
                db.delete(obj)
        db.commit()


def test_history_structure_et_pagination():
    btc, eth = _btc_eth_ids()
    base = client.get("/api/v1/trades/history").json()
    base_total = base["pagination"]["total"]

    t1 = _open_trade(btc)
    t2 = _open_trade(eth)
    _close(t2)

    r = client.get("/api/v1/trades/history")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"items", "pagination", "filters"}
    assert body["pagination"]["total"] == base_total + 2
    assert body["filters"]["date_field"] == "opened_at"
    assert body["filters"]["sort"] == "opened_at:desc"

    # pagination : limit=1 -> 1 item, has_more vrai
    r1 = client.get("/api/v1/trades/history?limit=1&offset=0")
    p = r1.json()["pagination"]
    assert p["returned"] == 1
    assert p["limit"] == 1
    assert p["has_more"] is True

    _cleanup([t1, t2])


def test_history_filtre_status_et_asset():
    btc, eth = _btc_eth_ids()
    t_open = _open_trade(btc)
    t_closed = _open_trade(btc)
    _close(t_closed)
    t_eth = _open_trade(eth)

    # status=closed
    closed = client.get("/api/v1/trades/history?status=closed").json()
    assert all(it["status"] == "closed" for it in closed["items"])
    assert t_closed in [it["id"] for it in closed["items"]]
    assert t_open not in [it["id"] for it in closed["items"]]

    # asset_id = BTC -> ne contient pas le trade ETH
    by_btc = client.get(f"/api/v1/trades/history?asset_id={btc}").json()
    ids = [it["id"] for it in by_btc["items"]]
    assert t_eth not in ids
    assert t_open in ids

    _cleanup([t_open, t_closed, t_eth])


def test_history_rejette_date_naive_et_intervalle_invalide():
    # datetime sans timezone -> 422
    r_naive = client.get("/api/v1/trades/history?from=2026-01-01T00:00:00")
    assert r_naive.status_code == 422
    # from > to -> 422
    r_range = client.get(
        "/api/v1/trades/history?from=2026-02-01T00:00:00Z&to=2026-01-01T00:00:00Z"
    )
    assert r_range.status_code == 422


def test_history_filtre_temporel_exclut_le_passe():
    btc, _ = _btc_eth_ids()
    t1 = _open_trade(btc)
    # to dans le passé -> notre trade (opened_at = maintenant) est exclu
    r = client.get("/api/v1/trades/history?to=2000-01-01T00:00:00Z")
    assert t1 not in [it["id"] for it in r.json()["items"]]
    _cleanup([t1])


def test_summary_filtre_par_asset():
    btc, eth = _btc_eth_ids()
    tb = _open_trade(btc)
    _close(tb, "150")  # BTC +500
    te = _open_trade(eth)
    _close(te, "80")  # ETH -200

    s = client.get(f"/api/v1/portfolio/summary?asset_id={btc}").json()
    assert s["filters"]["asset_id"] == btc
    symbols = {a["symbol"] for a in s["by_asset"]}
    assert symbols == {"BTC"}  # seul BTC dans le périmètre

    _cleanup([tb, te])


def test_summary_fenetre_future_est_vide():
    btc, _ = _btc_eth_ids()
    tb = _open_trade(btc)
    _close(tb, "150")
    # fenêtre dans le futur -> aucun closed -> réalisé à zéro, best/worst null
    s = client.get("/api/v1/portfolio/summary?from=2100-01-01T00:00:00Z").json()
    assert Decimal(str(s["realized"]["pnl_net"])) == Decimal("0.00")
    assert s["realized"]["pnl_percent"] is None
    assert s["best_asset"] is None
    assert s["by_asset"] == []
    _cleanup([tb])
