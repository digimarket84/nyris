"""Test 2 : meanrev DEBRIDE (compounding + plein capital, SANS levier) vs version bridee (100E fixe).
Meme capital de depart E0. Mesure le vrai plafond de gain de notre edge sans nos garde-fous. Lecture seule."""
from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.services import candles as cs
from sqlalchemy import select

ALTS = ["LINK", "AVAX", "NEAR", "DOGE", "SUI", "PEPE", "ENA", "WLD", "ZEC",
        "POND", "BABY", "HOME", "LA"]
TARGET = 2700
RT = 0.004
DAY = 86_400_000
E0 = 1000.0
db = SessionLocal()


def load(s):
    a = db.scalar(select(Asset).where(Asset.symbol == s))
    return cs.get_candles_paginated(a.binance_symbol, "1d", TARGET) if a and a.binance_symbol else None


def sma(arr, i, n):
    return sum(arr[i - n:i]) / n if i >= n else None


def rsi_series(arr, n):
    out = [None] * len(arr)
    if len(arr) <= n:
        return out
    g = sum(max(arr[i] - arr[i - 1], 0) for i in range(1, n + 1)) / n
    lo = sum(max(arr[i - 1] - arr[i], 0) for i in range(1, n + 1)) / n
    out[n] = 100 - 100 / (1 + (g / lo if lo else 1e9))
    for i in range(n + 1, len(arr)):
        d = arr[i] - arr[i - 1]
        g = (g * (n - 1) + max(d, 0)) / n
        lo = (lo * (n - 1) + max(-d, 0)) / n
        out[i] = 100 - 100 / (1 + (g / lo if lo else 1e9))
    return out


def trades_for(cands, buy=35, exsma=10, hold=20):
    """Retourne les trades (entry_ts, exit_ts, ret_net) — ret independant de la taille."""
    closes = [float(c.close) for c in cands]
    r14 = rsi_series(closes, 14)
    out, pos = [], None
    for i in range(len(cands)):
        if pos is not None and (i - pos["i"]) >= hold:
            out.append((pos["t"], cands[i].close_time, closes[i] / pos["p"] - 1 - RT)); pos = None
        r = r14[i]
        if r is None:
            continue
        if pos is None:
            if r < buy:
                pos = {"p": closes[i], "t": cands[i].close_time, "i": i}
        else:
            s = sma(closes, i, exsma)
            if s is not None and closes[i] > s:
                out.append((pos["t"], cands[i].close_time, closes[i] / pos["p"] - 1 - RT)); pos = None
    return out


def portfolio(all_trades, mode, weight=None, fixed=100.0, wstart=0):
    """Simule l'equity. mode='bride' (fixe, pas de compounding) ou 'debride' (compounding, poids w)."""
    ev = []
    for k, (ein, eout, ret) in enumerate(all_trades):
        if ein < wstart:
            continue
        ev.append((ein, 0, k, ret))   # 0=entree
        ev.append((eout, 1, k, ret))  # 1=sortie (traitee avant entree au meme ts)
    ev.sort(key=lambda x: (x[0], -x[1]))
    cash = E0
    open_pos = {}
    peak = E0
    maxdd = 0.0
    skipped = 0
    taken = 0
    for ts, typ, k, ret in ev:
        if typ == 1:
            if k in open_pos:
                size = open_pos.pop(k)
                cash += size * (1 + ret)
        else:
            equity = cash + sum(open_pos.values())
            if mode == "bride":
                size = min(fixed, cash)
            else:
                size = min(equity * weight, cash)
            if size > 1.0:
                cash -= size
                open_pos[k] = size
                taken += 1
            else:
                skipped += 1
        equity = cash + sum(open_pos.values())
        peak = max(peak, equity)
        maxdd = min(maxdd, equity / peak - 1)
    final = cash + sum(open_pos.values())
    return {"final": final, "ret": final / E0 - 1, "maxdd": maxdd,
            "taken": taken, "skipped": skipped}


data = {s: c for s in ALTS if (c := load(s))}
all_trades = []
for cands in data.values():
    all_trades += trades_for(cands)
all_trades.sort()
latest = max(c[-1].close_time for c in data.values())
n_years = (latest - min(t[0] for t in all_trades)) / (DAY * 365)
print(f"Univers={len(data)} alts | {len(all_trades)} trades | E0={E0:.0f}E | ~{n_years:.1f} ans\n")


def cagr(r):
    return ((1 + r) ** (1 / n_years) - 1) if r > -1 else -1


print("=== BRIDE (100E fixe, sans compounding) ===")
b = portfolio(all_trades, "bride", fixed=100.0)
print(f"  final={b['final']:.0f}E  rendt={b['ret']*100:+.0f}%  CAGR={cagr(b['ret'])*100:+.0f}%  "
      f"maxDD={b['maxdd']*100:.0f}%  trades pris={b['taken']} (skip cash={b['skipped']})")

print("\n=== DEBRIDE (compounding + plein capital, sans levier) ===")
print(f"{'poids/pos':<12}{'final':>12}{'rendt':>9}{'CAGR':>8}{'maxDD':>8}{'pris':>7}{'skip':>7}")
for w in (1 / 13, 1 / 10, 1 / 8, 1 / 6, 1 / 4, 1 / 3):
    d = portfolio(all_trades, "debride", weight=w)
    print(f"1/{1/w:>4.1f} ({w*100:>3.0f}%) {d['final']:>11.0f}E{d['ret']*100:>+8.0f}%"
          f"{cagr(d['ret'])*100:>+7.0f}%{d['maxdd']*100:>7.0f}%{d['taken']:>7}{d['skipped']:>7}")

print("\n=== DEBRIDE sur 365 derniers jours (poids 1/8) ===")
d = portfolio(all_trades, "debride", weight=1 / 8, wstart=latest - 365 * DAY)
print(f"  final={d['final']:.0f}E  rendt(1an)={d['ret']*100:+.0f}%  maxDD={d['maxdd']*100:.0f}%  trades={d['taken']}")
