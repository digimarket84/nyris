"""Backtest CROSS-SECTIONNEL daily (reco conseil #2). Rank les alts, long top-k/bottom-k, hebdo.
Juge = battre le PANIER equipondere (pas juste etre positif). Lecture seule. Net de couts."""
from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.services import candles as cs
from sqlalchemy import select

UNIV = ["BTC", "ETH", "SOL", "LINK", "AVAX", "NEAR", "DOGE", "SUI", "PEPE",
        "ENA", "WLD", "ZEC", "POND", "BABY", "HOME", "LA"]
TARGET = 2700
RT = 0.004
DAY = 86_400_000
STEP = 7          # rebalance hebdo (7 bougies daily)
db = SessionLocal()


def load(s):
    a = db.scalar(select(Asset).where(Asset.symbol == s))
    return cs.get_candles_paginated(a.binance_symbol, "1d", TARGET) if a and a.binance_symbol else None


data = {}
for s in UNIV:
    c = load(s)
    if c:
        data[s] = {x.close_time: float(x.close) for x in c}
# calendrier de reference = union triee des dates
cal = sorted(set().union(*[set(d.keys()) for d in data.values()]))
latest = cal[-1]


def ret(sym, t_from, t_to):
    d = data[sym]
    if t_from in d and t_to in d and d[t_from] > 0:
        return d[t_to] / d[t_from] - 1
    return None


def run(mode, k, lookback):
    """mode momentum (long top-k) ou meanrev (long bottom-k). Renvoie liste de (date, ret_porte)."""
    out = []
    for ii in range(lookback, len(cal) - STEP, STEP):
        t = cal[ii]
        tb = cal[ii - lookback]
        tf = cal[ii + STEP]
        scores = []
        for s in data:
            r = ret(s, tb, t)
            fwd = ret(s, t, tf)
            if r is not None and fwd is not None:
                scores.append((s, r, fwd))
        if len(scores) < 6:
            continue
        scores.sort(key=lambda z: z[1], reverse=(mode == "momentum"))
        sel = scores[:k]
        pret = sum(z[2] for z in sel) / len(sel) - RT          # turnover plein
        basket = sum(z[2] for z in scores) / len(scores)        # panier equipondere (sans cout, hold)
        out.append((t, pret, basket))
    return out


def equity_stats(series, key, wstart):
    eq = 1.0
    peak = 1.0
    dd = 0.0
    n = 0
    for t, pret, basket in series:
        if t < wstart:
            continue
        r = pret if key == "strat" else basket
        eq *= (1 + r)
        peak = max(peak, eq)
        dd = min(dd, eq / peak - 1)
        n += 1
    return eq - 1, dd, n


def windows():
    return [("tout", 0), ("365j", latest - 365 * DAY), ("180j", latest - 180 * DAY),
            ("90j", latest - 90 * DAY)]


print(f"Cross-sectionnel | {len(data)} actifs | rebalance hebdo | net {RT*100:.1f}%/pos\n")
CONFIGS = [
    ("XS Momentum top3 (30d)", "momentum", 3, 30),
    ("XS Momentum top5 (30d)", "momentum", 5, 30),
    ("XS Momentum top3 (90d)", "momentum", 3, 90),
    ("XS MeanRev bottom3 (5d)", "meanrev", 3, 5),
    ("XS MeanRev bottom5 (5d)", "meanrev", 5, 5),
    ("XS MeanRev bottom3 (14d)", "meanrev", 3, 14),
]
hdr = f"{'Strategie':<26}" + "".join(f"{w[0]:>30}" for w in windows())
print(hdr)
print("-" * len(hdr))
for name, mode, k, lb in CONFIGS:
    series = run(mode, k, lb)
    row = f"{name:<26}"
    for _, ws in windows():
        sret, sdd, n = equity_stats(series, "strat", ws)
        bret, bdd, _ = equity_stats(series, "basket", ws)
        lift = sret - bret
        row += f"{f'{sret*100:+.0f}% vs pan{bret*100:+.0f}% (L{lift*100:+.0f},DD{sdd*100:.0f},n{n})':>30}"
    print(row)
print()
print("Lecture : 'L' = lift vs panier equipondere (DOIT etre >0 pour un edge). DD=maxdrawdown.")
