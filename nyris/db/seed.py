"""Insertion idempotente de la watchlist initiale.

Usage :  python -m nyris.db.seed
"""

from __future__ import annotations

from sqlalchemy import select

from nyris.core.database import SessionLocal
from nyris.models.asset import Asset

# (symbol, name) — watchlist V1
WATCHLIST: list[tuple[str, str]] = [
    ("BTC", "Bitcoin"),
    ("ETH", "Ethereum"),
    ("SOL", "Solana"),
    ("TAO", "Bittensor"),
    ("FET", "Fetch.ai"),
    ("RNDR", "Render"),
    ("AETH", "AETH"),
]


def seed_assets() -> None:
    created = 0
    with SessionLocal() as db:
        for symbol, name in WATCHLIST:
            exists = db.scalar(select(Asset).where(Asset.symbol == symbol))
            if exists is None:
                db.add(Asset(symbol=symbol, name=name, quote_currency="EUR", is_active=True))
                created += 1
        db.commit()
    print(
        f"Seed terminé : {created} actif(s) ajouté(s), {len(WATCHLIST) - created} déjà présent(s)."
    )


if __name__ == "__main__":
    seed_assets()
