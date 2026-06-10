"""Re-seed des binance_symbol (pytest les efface sur la prod). Idempotent.
A relancer apres CHAQUE pytest sur le VPS : PYTHONPATH=. python scripts/seed_binance_symbols.py
Versionne dans le repo pour survivre aux reboots (/tmp est ephemere)."""
from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from sqlalchemy import select

MAP = {
    "BTC": "BTCEUR", "ETH": "ETHEUR", "SOL": "SOLEUR", "AVAX": "AVAXEUR",
    "DOGE": "DOGEEUR", "LINK": "LINKEUR", "NEAR": "NEAREUR", "PEPE": "PEPEEUR",
    "SUI": "SUIEUR",
    "BABY": "BABYUSDT", "ENA": "ENAUSDT", "HOME": "HOMEUSDT", "LA": "LAUSDT",
    "POND": "PONDUSDT", "WLD": "WLDUSDT", "ZEC": "ZECUSDT",
}

db = SessionLocal()
n = 0
for sym, bsym in MAP.items():
    a = db.scalar(select(Asset).where(Asset.symbol == sym))
    if a is None:
        print(f"  absent: {sym} (non cree)")
        continue
    if a.binance_symbol != bsym or not a.is_tradeable:
        a.binance_symbol = bsym
        a.is_tradeable = True
        n += 1
db.commit()
print(f"re-seed termine : {n} actifs mis a jour / {len(MAP)} mappes")
