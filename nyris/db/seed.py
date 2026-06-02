"""Insertion/mise à jour idempotente de la watchlist initiale.

- upsert par ``symbol``
- met à jour les actifs existants (display_name, exchange_symbol, status, ...)
- supprime les actifs obsolètes qui ne sont référencés par aucun trade

Usage :  python -m nyris.db.seed
"""

from __future__ import annotations

from sqlalchemy import select

from nyris.core.database import SessionLocal
from nyris.models.asset import Asset, AssetStatus
from nyris.models.simulated_trade import SimulatedTrade

WATCHLIST: list[dict] = [
    {
        "symbol": "BTC", "display_name": "Bitcoin", "exchange_symbol": "BTC",
        "status": AssetStatus.active, "is_tradeable": True, "notes": None,
    },
    {
        "symbol": "ETH", "display_name": "Ethereum", "exchange_symbol": "ETH",
        "status": AssetStatus.active, "is_tradeable": True, "notes": None,
    },
    {
        "symbol": "SOL", "display_name": "Solana", "exchange_symbol": "SOL",
        "status": AssetStatus.active, "is_tradeable": True, "notes": None,
    },
    {
        "symbol": "TAO", "display_name": "Bittensor", "exchange_symbol": "TAO",
        "status": AssetStatus.active, "is_tradeable": True, "notes": None,
    },
    {
        "symbol": "FET", "display_name": "Fetch.ai", "exchange_symbol": "FET",
        "status": AssetStatus.active, "is_tradeable": True, "notes": None,
    },
    {
        "symbol": "RENDER", "display_name": "Render", "exchange_symbol": "RENDER",
        "status": AssetStatus.active, "is_tradeable": True, "notes": None,
    },
    {
        "symbol": "ATH", "display_name": "Aethir", "exchange_symbol": "ATH",
        "status": AssetStatus.watch_only, "is_tradeable": False,
        "notes": "Tracked for analysis, not currently listed on Binance Spot standard",
    },
]


def seed_assets() -> None:
    target_symbols = {a["symbol"] for a in WATCHLIST}
    created = updated = removed = 0

    with SessionLocal() as db:
        # upsert de la watchlist
        for data in WATCHLIST:
            obj = db.scalar(select(Asset).where(Asset.symbol == data["symbol"]))
            if obj is None:
                db.add(Asset(quote_currency="EUR", **data))
                created += 1
            else:
                obj.display_name = data["display_name"]
                obj.exchange_symbol = data["exchange_symbol"]
                obj.status = data["status"]
                obj.is_tradeable = data["is_tradeable"]
                obj.notes = data["notes"]
                updated += 1

        # purge des actifs obsolètes (ex. anciens AETH / RNDR) sans trade associé
        obsolete = db.scalars(select(Asset).where(Asset.symbol.notin_(target_symbols))).all()
        for obj in obsolete:
            referenced = db.scalar(
                select(SimulatedTrade.id).where(SimulatedTrade.asset_id == obj.id).limit(1)
            )
            if referenced is None:
                db.delete(obj)
                removed += 1

        db.commit()

    print(f"Seed: +{created} ajout, ~{updated} maj, -{removed} retire(s).")


if __name__ == "__main__":
    seed_assets()
