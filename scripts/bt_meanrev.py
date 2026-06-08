"""Round 2 : famille MEAN-REVERSION sur 4h (assez de trades pour juger le RECENT).
Le marche est devenu mean-reverting -> on cherche l'edge la. Lecture seule.
Fenetres: tout / 365j / 180j / 90j / 30j / 7j. Sizing 100 EUR/trade net de 0.4% AR.
"""
from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.services import candles as cs
from sqlalchemy import select

UNIVERSE = ["BTC", "ETH", "SOL", "LINK", "AVAX", "NEAR", "DOGE"]
TF = "4h"
TARGET = 6600
NOTIONAL = 100.0
RT_COST = 0.004
DAY = 86_400_000
db = SessionLocal()


def load(sym):
    a = db.scalar(select(Asset).where(Asset.symbol == sym))
    return cs.get_candles_paginated(a.binance_symbol, TF, TARGET) if a and a.binance_symbol else None


def sma(arr, i, n):
    return sum(arr[i - n:i]) / n if i >= n else None


def std(arr, i, n):
    if i < n:
        return None
    m = sum(arr[i - n:i]) / n
    return (sum((x - m) ** 2 for x in arr[i - n:i]) / n) ** 0.5


def rsi_series(arr, n=14):
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


def run_state(cands, want_fn):
    closes = [float(c.close) for c in cands]
    ctx = {"closes": closes, "r2": rsi_series(closes, 2), "r14": rsi_series(closes, 14)}
    trades, pos = [], None
    for i in range(len(cands)):
        w = want_fn(ctx, i)
        if w is None:
            continue
        if pos is None and w:
            pos = {"pe": closes[i], "et": cands[i].close_time}
        elif pos is not None and not w:
            pe, px = pos["pe"], closes[i]
            trades.append({"net": NOTIONAL * (px - pe) / pe - NOTIONAL * RT_COST,
                           "et": pos["et"], "xt": cands[i].close_time})
            pos = None
    return trades


# strategies (etat desire long)
def mr_rsi2(buy, sellk, trend=None):
    def f(ctx, i):
        r = ctx["r2"][i]
        if r is None:
            return None
        if trend is not None:
            m = sma(ctx["closes"], i, trend)
            if m is None:
                return None
            if ctx["closes"][i] <= m:
                return False
        s5 = sma(ctx["closes"], i, sellk)
        if s5 is None:
            return None
        if r < buy:
            return True
        if ctx["closes"][i] > s5:
            return False
        return None
    return f


def mr_rsi14(buy, sell, trend=None):
    def f(ctx, i):
        r = ctx["r14"][i]
        if r is None:
            return None
        if trend is not None:
            m = sma(ctx["closes"], i, trend)
            if m is None:
                return None
            if ctx["closes"][i] <= m:
                return False
        if r < buy:
            return True
        if r > sell:
            return False
        return None
    return f


def mr_boll(n=20, k=2.0, trend=None):
    def f(ctx, i):
        m = sma(ctx["closes"], i, n)
        sd = std(ctx["closes"], i, n)
        if m is None or sd is None:
            return None
        c = ctx["closes"][i]
        if trend is not None:
            mt = sma(ctx["closes"], i, trend)
            if mt is None:
                return None
            if c <= mt:
                return False
        if c < m - k * sd:
            return True
        if c > m:
            return False
        return None
    return f


def windows(latest):
    return [("tout", 0), ("365j", latest - 365 * DAY), ("180j", latest - 180 * DAY),
            ("90j", latest - 90 * DAY), ("30j", latest - 30 * DAY), ("7j", latest - 7 * DAY)]


def maxdd(ts):
    eq = peak = dd = 0.0
    for t in ts:
        eq += t["net"]
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return dd


def agg(trades, ws):
    sel = [t for t in trades if t["et"] >= ws]
    if not sel:
        return None
    nets = [t["net"] for t in sel]
    gp = sum(x for x in nets if x > 0)
    gl = -sum(x for x in nets if x < 0)
    return {"n": len(sel), "net": sum(nets), "pf": gp / gl if gl else 999.0,
            "win": 100 * sum(1 for x in nets if x > 0) / len(sel)}


data = {s: c for s in UNIVERSE if (c := load(s))}
latest = max(c[-1].close_time for c in data.values())
WINS = windows(latest)

STRATS = [
    ("MR RSI2<5 exitSMA5 noflt", mr_rsi2(5, 5)),
    ("MR RSI2<10 exitSMA5 noflt", mr_rsi2(10, 5)),
    ("MR RSI2<10 exitSMA10 noflt", mr_rsi2(10, 10)),
    ("MR RSI2<10 exitSMA5 flt200", mr_rsi2(10, 5, 200)),
    ("MR RSI2<5 exitSMA10 flt100", mr_rsi2(5, 10, 100)),
    ("MR RSI14<30 exit55 noflt", mr_rsi14(30, 55)),
    ("MR RSI14<25 exit60 noflt", mr_rsi14(25, 60)),
    ("MR RSI14<30 exit55 flt200", mr_rsi14(30, 55, 200)),
    ("MR Boll20/2 exitMid noflt", mr_boll(20, 2.0)),
    ("MR Boll20/2.5 exitMid noflt", mr_boll(20, 2.5)),
    ("MR Boll20/2 exitMid flt200", mr_boll(20, 2.0, 200)),
]

print(f"TF={TF} | {', '.join(f'{k}={len(v)}' for k, v in data.items())}")
hdr = f"{'Strategie':<30}" + "".join(f"{w[0]:>24}" for w in WINS)
print(hdr)
print("-" * len(hdr))
for name, fn in STRATS:
    alltr = []
    for cands in data.values():
        alltr += run_state(cands, fn)
    row = f"{name:<30}"
    for _, ws in WINS:
        a = agg(alltr, ws)
        if a is None:
            row += f"{'-':>24}"
        else:
            cell = f"{a['net']:+.0f}E n{a['n']} PF{a['pf']:.2f}w{a['win']:.0f}"
            row += f"{cell:>24}"
    print(row)
