"""Seed/re-seed des 100 actifs USDT de l'univers meanrev-v2 (idempotent).
A relancer apres CHAQUE pytest (qui efface binance_symbol) :
  PYTHONPATH=. python scripts/seed_universe_v2.py
"""
from sqlalchemy import select

from nyris.core.database import SessionLocal
from nyris.models.asset import Asset, AssetStatus
from nyris.strategy.meanrev_v2_universe import PAIRS

db = SessionLocal()
created = updated = 0
for pair in PAIRS:
    base = pair[:-4]
    a = db.scalar(select(Asset).where(Asset.symbol == pair))
    if a is None:
        db.add(Asset(
            symbol=pair, display_name=base, exchange_symbol=pair, quote_currency="USDT",
            status=AssetStatus.active, is_tradeable=True, binance_symbol=pair,
            notes="auto:univers-v2"))
        created += 1
    elif a.binance_symbol != pair or not a.is_tradeable:
        a.binance_symbol = pair
        a.is_tradeable = True
        updated += 1
db.commit()
print(f"univers v2 : {created} crees, {updated} mis a jour / {len(PAIRS)}")
