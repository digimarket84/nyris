"""Backtest de la REGLE D'ADAPTATION (kill-switch) sur l'edge meanrev, AVANT de la deployer.
Question : pauser les entrees quand le PF glissant casse ameliore-t-il, ou coupe-t-il l'edge
au mauvais moment ? Compare always-on vs gated (+ sizing pilote par perf glissante). Lecture seule."""
from collections import deque
from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.services import candles as cs
from sqlalchemy import select

ALTS = ["LINK", "AVAX", "NEAR", "DOGE", "SUI", "PEPE", "ENA", "WLD", "ZEC",
        "POND", "BABY", "HOME", "LA"]
TARGET = 2700
RT = 0.004
db = SessionLocal()


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


def mr_trades(cands):
    closes = [float(c.close) for c in cands]
    r14 = rsi_series(closes, 14)
    out, pos = [], None
    for i in range(len(cands)):
        if pos is not None and (i - pos["i"]) >= 20:
            out.append((pos["ct"], cands[i].close_time, closes[i] / pos["p"] - 1 - RT)); pos = None
        r = r14[i]
        if r is None:
            continue
        if pos is None:
            if r < 35:
                pos = {"p": closes[i], "i": i, "ct": cands[i].close_time}
        else:
            s = sma(closes, i, 10)
            if s is not None and closes[i] > s:
                out.append((pos["ct"], cands[i].close_time, closes[i] / pos["p"] - 1 - RT)); pos = None
    return out


trades = []
for s in ALTS:
    a = db.scalar(select(Asset).where(Asset.symbol == s))
    if a and a.binance_symbol:
        trades += mr_trades(cs.get_candles_paginated(a.binance_symbol, "1d", TARGET))
trades.sort(key=lambda t: t[0])  # par date d'entree


def metrics(rets):
    if not rets:
        return "0 trade"
    gp = sum(x for x in rets if x > 0); gl = -sum(x for x in rets if x < 0)
    eq = 0.0; peak = 0.0; dd = 0.0
    for r in rets:
        eq += r; peak = max(peak, eq); dd = min(dd, eq - peak)
    pf = gp / gl if gl else 999
    return (f"n={len(rets):<4} net={100*sum(rets):+7.1f}%  PF={pf:.2f}  "
            f"win={100*sum(1 for x in rets if x>0)/len(rets):3.0f}%  maxDD={100*dd:5.1f}%")


# baseline always-on (ordre de cloture pour la courbe)
base = [t[2] for t in sorted(trades, key=lambda t: t[1])]
print("=== BASELINE always-on ===")
print("  " + metrics(base))


def simulate_gate(N, pf_low, pf_high):
    """Gate event-driven : PF glissant sur N dernieres CLOTURES ; pause entrees si <low, reprise si >high.
    La fenetre glissante voit TOUS les outcomes (shadow-tracking) pour detecter la reprise."""
    ev = []
    for k, (ein, eout, ret) in enumerate(trades):
        ev.append((ein, 0, k, ret))   # entree
        ev.append((eout, 1, k, ret))  # cloture
    ev.sort(key=lambda x: (x[0], x[1]))
    win = deque(maxlen=N)
    gate = True
    taken_at_entry = {}
    taken_rets = []
    for ts, typ, k, ret in ev:
        if typ == 0:
            taken_at_entry[k] = gate            # snapshot du gate a l'entree
        else:
            if taken_at_entry.get(k):
                taken_rets.append((ts, ret))
            win.append(ret)                     # shadow : tous les outcomes
            if len(win) >= N:
                gp = sum(x for x in win if x > 0); gl = -sum(x for x in win if x < 0)
                pf = gp / gl if gl else 999
                if pf < pf_low:
                    gate = False
                elif pf > pf_high:
                    gate = True
    taken_rets.sort()
    return [r for _, r in taken_rets]


print("\n=== GATED (kill-switch PF glissant) ===")
for N in (15, 20, 30):
    for low, high in [(1.0, 1.0), (1.0, 1.3), (0.8, 1.2)]:
        g = simulate_gate(N, low, high)
        print(f"  N={N} pause<PF{low}/reprise>PF{high} : {metrics(g)}")


# sizing pilote par perf glissante (continu, pas binaire)
def simulate_sizing(N):
    ev = []
    for k, (ein, eout, ret) in enumerate(trades):
        ev.append((ein, 0, k, ret))
        ev.append((eout, 1, k, ret))
    ev.sort(key=lambda x: (x[0], x[1]))
    win = deque(maxlen=N)
    size_at_entry = {}
    taken = []
    for ts, typ, k, ret in ev:
        if typ == 0:
            if len(win) >= N:
                gp = sum(x for x in win if x > 0); gl = -sum(x for x in win if x < 0)
                pf = gp / gl if gl else 2.0
                size_at_entry[k] = max(0.0, min(1.5, (pf - 0.8) / 0.9))  # 0 si PF<0.8, 1.5 si PF>=2.15
            else:
                size_at_entry[k] = 1.0
        else:
            f = size_at_entry.get(k, 1.0)
            taken.append((ts, ret * f))
            win.append(ret)
    taken.sort()
    return [r for _, r in taken]


print("\n=== SIZING pilote par PF glissant (continu) ===")
for N in (20, 30):
    print(f"  N={N} : {metrics(simulate_sizing(N))}")
