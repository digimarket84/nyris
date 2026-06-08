"""Round 3 : MEAN-REVERSION daily, univers large, focus fenetres recentes. Lecture seule.
Sizing 100 EUR/trade net de 0.4% AR. Cap de duree optionnel (anti bag-holding)."""
from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.services import candles as cs
from sqlalchemy import select

UNIVERSE = ["BTC", "ETH", "SOL", "LINK", "AVAX", "NEAR", "DOGE", "SUI", "PEPE",
            "ENA", "WLD", "ZEC", "POND", "BABY", "HOME", "LA"]
TF = "1d"
TARGET = 2700
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


def run_state(cands, want_fn, max_hold=None):
    closes = [float(c.close) for c in cands]
    ctx = {"closes": closes, "r2": rsi_series(closes, 2),
           "r3": rsi_series(closes, 3), "r14": rsi_series(closes, 14)}
    trades, pos = [], None
    for i in range(len(cands)):
        if pos is not None and max_hold is not None and (i - pos["i"]) >= max_hold:
            pe, px = pos["pe"], closes[i]
            trades.append({"net": NOTIONAL * (px - pe) / pe - NOTIONAL * RT_COST,
                           "et": pos["et"], "xt": cands[i].close_time})
            pos = None
        w = want_fn(ctx, i)
        if w is None:
            continue
        if pos is None and w:
            pos = {"pe": closes[i], "et": cands[i].close_time, "i": i}
        elif pos is not None and not w:
            pe, px = pos["pe"], closes[i]
            trades.append({"net": NOTIONAL * (px - pe) / pe - NOTIONAL * RT_COST,
                           "et": pos["et"], "xt": cands[i].close_time})
            pos = None
    return trades


def mr_rsi(period, buy, exit_mode, exit_val, trend=None):
    key = {2: "r2", 3: "r3", 14: "r14"}[period]

    def f(ctx, i):
        r = ctx[key][i]
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
        if exit_mode == "sma":
            s = sma(ctx["closes"], i, exit_val)
            if s is None:
                return None
            if ctx["closes"][i] > s:
                return False
        else:  # exit_mode == "rsi"
            if r > exit_val:
                return False
        return None
    return f


def mr_boll(n, k, trend=None):
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
            ("90j", latest - 90 * DAY), ("30j", latest - 30 * DAY)]


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
    ("RSI2<5 exSMA5 nofilt h10", mr_rsi(2, 5, "sma", 5), 10),
    ("RSI2<10 exSMA5 nofilt h10", mr_rsi(2, 10, "sma", 5), 10),
    ("RSI2<10 exSMA5 flt100 h10", mr_rsi(2, 10, "sma", 5, 100), 10),
    ("RSI2<10 exSMA5 flt200 h15", mr_rsi(2, 10, "sma", 5, 200), 15),
    ("RSI3<15 exSMA5 nofilt h10", mr_rsi(3, 15, "sma", 5), 10),
    ("RSI3<15 exSMA10 flt100 h15", mr_rsi(3, 15, "sma", 10, 100), 15),
    ("RSI14<25 exRSI60 nofilt h20", mr_rsi(14, 25, "rsi", 60), 20),
    ("RSI14<30 exRSI55 nofilt h20", mr_rsi(14, 30, "rsi", 55), 20),
    ("RSI14<30 exRSI55 flt100 h20", mr_rsi(14, 30, "rsi", 55, 100), 20),
    ("RSI14<35 exSMA10 nofilt h15", mr_rsi(14, 35, "sma", 10), 15),
    ("Boll20/2 exMid nofilt h15", mr_boll(20, 2.0), 15),
    ("Boll20/2.5 exMid nofilt h15", mr_boll(20, 2.5), 15),
    ("Boll20/2.5 exMid flt100 h15", mr_boll(20, 2.5, 100), 15),
]

print(f"TF={TF} | {len(data)} actifs | net EUR (n trades, PF, win%) par fenetre")
hdr = f"{'Strategie':<30}" + "".join(f"{w[0]:>22}" for w in WINS)
print(hdr)
print("-" * len(hdr))
for name, fn, mh in STRATS:
    alltr = []
    for cands in data.values():
        alltr += run_state(cands, fn, max_hold=mh)
    row = f"{name:<30}"
    for _, ws in WINS:
        a = agg(alltr, ws)
        if a is None:
            row += f"{'-':>22}"
        else:
            cell = f"{a['net']:+.0f} n{a['n']} PF{a['pf']:.2f}w{a['win']:.0f}"
            row += f"{cell:>22}"
    print(row)
