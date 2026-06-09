"""Analyse comparative live de toutes les strategies. Lecture seule."""
from nyris.core.database import SessionLocal
from nyris.models.pattern_trade import PatternTrade
from nyris.models.short_trade import ShortTrade
from nyris.models.asset import Asset
from nyris.services import candles as cs
from sqlalchemy import select, func

db = SessionLocal()


def closed_stats(run_id):
    rows = db.execute(select(PatternTrade.pnl_net).where(
        PatternTrade.run_id == run_id, PatternTrade.status == "closed")).scalars().all()
    nets = [float(x) for x in rows if x is not None]
    if not nets:
        return None
    gp = sum(x for x in nets if x > 0)
    gl = -sum(x for x in nets if x < 0)
    return {"n": len(nets), "net": sum(nets), "win": 100 * sum(1 for x in nets if x > 0) / len(nets),
            "pf": gp / gl if gl else 999, "avg": sum(nets) / len(nets),
            "best": max(nets), "worst": min(nets)}


print("=== REALISE par strategie (pattern_trades closed) ===")
print(f"{'run_id':<22}{'n':>5}{'win%':>6}{'net E':>9}{'avg':>8}{'PF':>6}{'pire':>8}{'best':>8}")
runs = db.execute(select(PatternTrade.run_id).where(PatternTrade.status == "closed")
                  .group_by(PatternTrade.run_id)).scalars().all()
for r in sorted(runs):
    s = closed_stats(r)
    if s:
        print(f"{r:<22}{s['n']:>5}{s['win']:>6.0f}{s['net']:>9.2f}{s['avg']:>8.3f}"
              f"{s['pf']:>6.2f}{s['worst']:>8.2f}{s['best']:>8.2f}")

# short
sr = db.execute(select(ShortTrade.pnl_net).where(ShortTrade.status == "closed")).scalars().all()
snets = [float(x) for x in sr if x is not None]
if snets:
    gp = sum(x for x in snets if x > 0)
    gl = -sum(x for x in snets if x < 0)
    print(f"{'short_v4 (short_trades)':<22}{len(snets):>5}"
          f"{100*sum(1 for x in snets if x>0)/len(snets):>6.0f}{sum(snets):>9.2f}"
          f"{sum(snets)/len(snets):>8.3f}{(gp/gl if gl else 999):>6.2f}"
          f"{min(snets):>8.2f}{max(snets):>8.2f}")

print()
print("=== FLOTTANT positions MEANREV ouvertes (entry vs prix actuel) ===")
print(f"{'actif':<7}{'entry':>13}{'actuel':>13}{'var%':>8}{'jours':>7}{'flottant E':>12}")
opens = db.execute(select(PatternTrade, Asset.symbol, Asset.binance_symbol)
                   .join(Asset, Asset.id == PatternTrade.asset_id)
                   .where(PatternTrade.run_id == "live-meanrev-v1",
                          PatternTrade.status == "open")).all()
import datetime as dt
tot_float = 0.0
for t, sym, bsym in opens:
    try:
        c = cs.get_candles(bsym, "1d", 3)
        last = float(c[-1].close)
    except Exception:
        last = None
    if last is None:
        print(f"{sym:<7}{'?':>13}")
        continue
    entry = float(t.entry_price)
    var = (last - entry) / entry * 100
    days = (dt.datetime.now(dt.timezone.utc) - t.opened_at).days
    # flottant net approx : valeur sortie - notional - couts entree deja payes - cout sortie estime
    qty = float(t.quantity)
    notional = float(t.amount_invested)
    exit_val = qty * last
    exit_cost = exit_val * (0.001 + 0.0005 / 2 + 0.0005)
    floatv = (exit_val - notional) - float(t.entry_cost) - exit_cost
    tot_float += floatv
    print(f"{sym:<7}{entry:>13.6f}{last:>13.6f}{var:>8.1f}{days:>7}{floatv:>12.2f}")
print(f"{'TOTAL flottant meanrev':<40}{tot_float:>12.2f}")

print()
print("=== TREND (live-trend-v1) ===")
nt = db.scalar(select(func.count()).where(PatternTrade.run_id == "live-trend-v1"))
print(f"trades={nt} (en cash, attend une cassure Donchian-100 haussiere)")
