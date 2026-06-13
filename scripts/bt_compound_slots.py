"""Compte 50E avec K slots COMPOUNDES : quand un trade ferme, capital+gains repart sur le
prochain signal. size = equity/K (grossit avec l'equity). Capacite : si tous les slots sont
pleins, le signal est RATE. Backtest meanrev (RSI14<35) sur l'univers v2, ~90j. Lecture seule."""
import heapq

from nyris.services import candles as cs
from nyris.strategy.meanrev_v2_universe import PAIRS

RT = 0.004
DAY = 86_400_000
E0 = 50.0
WINDOW = 90


def sma(a, i, n):
    return sum(a[i - n:i]) / n if i >= n else None


def rsi_series(a, n):
    out = [None] * len(a)
    if len(a) <= n:
        return out
    g = sum(max(a[i] - a[i - 1], 0) for i in range(1, n + 1)) / n
    lo = sum(max(a[i - 1] - a[i], 0) for i in range(1, n + 1)) / n
    out[n] = 100 - 100 / (1 + (g / lo if lo else 1e9))
    for i in range(n + 1, len(a)):
        d = a[i] - a[i - 1]
        g = (g * (n - 1) + max(d, 0)) / n
        lo = (lo * (n - 1) + max(-d, 0)) / n
        out[i] = 100 - 100 / (1 + (g / lo if lo else 1e9))
    return out


def mr_trades(c):
    cl = [float(x.close) for x in c]
    r = rsi_series(cl, 14)
    out, pos = [], None
    for i in range(len(c)):
        if pos is not None and (i - pos[1]) >= 20:
            out.append((pos[2], c[i].close_time, cl[i] / pos[0] - 1 - RT)); pos = None
        if r[i] is None:
            continue
        if pos is None:
            if r[i] < 35:
                pos = (cl[i], i, c[i].close_time)
        else:
            s = sma(cl, i, 10)
            if s is not None and cl[i] > s:
                out.append((pos[2], c[i].close_time, cl[i] / pos[0] - 1 - RT)); pos = None
    return out


# collecte tous les trades
all_tr = []
for s in PAIRS:
    try:
        c = cs.get_candles(s, "1d", 130)
    except Exception:
        continue
    if len(c) < 40:
        continue
    all_tr += mr_trades(c)
latest = max(t[1] for t in all_tr)
start = latest - WINDOW * DAY
trades = sorted([t for t in all_tr if t[0] >= start], key=lambda t: t[0])
print(f"univers v2 | {len(trades)} trades meanrev sur {WINDOW}j | compte E0={E0:.0f}E\n")


def simulate(K):
    cash = E0
    exits = []  # heap (exit_ct, size, ret)
    ti = 0
    peak = E0
    maxdd = 0.0
    taken = skipped = 0
    while ti < len(trades) or exits:
        ne = trades[ti][0] if ti < len(trades) else None
        nx = exits[0][0] if exits else None
        if nx is not None and (ne is None or nx <= ne):
            _, size, ret = heapq.heappop(exits)
            cash += size * (1 + ret)
            eq = cash + sum(s for _, s, _ in exits)
            peak = max(peak, eq)
            maxdd = min(maxdd, eq / peak - 1)
        else:
            ein, eout, ret = trades[ti]
            ti += 1
            if len(exits) < K:
                eq = cash + sum(s for _, s, _ in exits)
                size = min(eq / K, cash)
                if size > 0.01:
                    cash -= size
                    heapq.heappush(exits, (eout, size, ret))
                    taken += 1
                else:
                    skipped += 1
            else:
                skipped += 1
    return cash, taken, skipped, maxdd


print(f"{'slots K':<10}{'taille init':<13}{'final':>9}{'rendt':>9}{'pris':>7}{'rates':>7}{'maxDD':>8}")
for K in (50, 25, 10, 5):
    fin, tk, sk, dd = simulate(K)
    print(f"{K:<10}{f'{E0/K:.2f}E/slot':<13}{fin:>8.2f}E{100*(fin/E0-1):>+8.1f}%{tk:>7}{sk:>7}{100*dd:>7.0f}%")
print()
print("rates = signaux manques car tous les slots pleins (contrainte de capacite).")
