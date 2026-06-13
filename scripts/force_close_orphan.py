"""Ferme une position orpheline (donnees gelees) au prix live.

Usage : python scripts/force_close_orphan.py <trade_id>
Cas LRC id=464 : ouverte sur bougie perimee (31/03), bloquee en already_processed.
PnL marque exit_orphan_stale -> a exclure des stats d'edge (entree fictive).
"""
import datetime as dt
import json
import sys
import urllib.request
from decimal import Decimal

from sqlalchemy import select

from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.models.pattern_trade import PatternTrade
from nyris.strategy import pattern_pnl

tid = int(sys.argv[1]) if len(sys.argv) > 1 else 464
db = SessionLocal()
t = db.scalar(select(PatternTrade).where(PatternTrade.id == tid, PatternTrade.status == "open"))
if t is None:
    print(f"trade id={tid} introuvable ou deja ferme")
    raise SystemExit
sym = db.scalar(select(Asset.binance_symbol).where(Asset.id == t.asset_id))
price = float(json.loads(urllib.request.urlopen(
    f"https://api.binance.com/api/v3/ticker/price?symbol={sym}", timeout=20).read())["price"])
now = dt.datetime.now(dt.timezone.utc)
hrs = max((now - t.opened_at).total_seconds() / 3600, 0.0)
res = pattern_pnl.compute_close(t.side, t.amount_invested, t.quantity, t.entry_cost,
                                Decimal(str(price)), t, hrs)
t.exit_price = Decimal(str(price))
t.exit_cost = res.exit_cost
t.funding_cost = res.funding_cost
t.pnl_gross = res.pnl_gross
t.pnl_net = res.pnl_net
t.pnl_percent = res.pnl_percent
t.exit_reason = "exit_orphan_stale"
t.status = "closed"
t.closed_at = now
db.commit()
print(f"FERME {sym} (id={tid}) @ {price} | pnl_net={float(res.pnl_net):+.2f}E "
      f"({float(res.pnl_percent):+.1f}%) reason=exit_orphan_stale")
