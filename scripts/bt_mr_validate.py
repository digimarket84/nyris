"""Round 4 : validation du candidat RSI14 mean-reversion daily.
A) plateau de parametres (robuste vs curve-fit)  B) perf par actif  C) sensibilite aux couts.
Lecture seule. Sizing 100 EUR/trade."""
from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.services import candles as cs
from sqlalchemy import select

UNIVERSE = ["BTC", "ETH", "SOL", "LINK", "AVAX", "NEAR", "DOGE", "SUI", "PEPE",
            "ENA", "WLD", "ZEC", "POND", "BABY", "HOME", "LA"]
TARGET = 2700
NOTIONAL = 100.0
DAY = 86_400_000
db = SessionLocal()


def load(sym):
    a = db.scalar(select(Asset).where(Asset.symbol == sym))
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


def run(cands, buy, exit_sma, hold, rt):
    closes = [float(c.close) for c in cands]
    r14 = rsi_series(closes, 14)
    trades, pos = [], None
    for i in range(len(cands)):
        if pos is not None and (i - pos["i"]) >= hold:
            trades.append({"net": NOTIONAL * (closes[i] - pos["pe"]) / pos["pe"] - NOTIONAL * rt,
                           "et": pos["et"]})
            pos = None
        r = r14[i]
        if r is None:
            continue
        s = sma(closes, i, exit_sma)
        if pos is None:
            if r < buy:
                pos = {"pe": closes[i], "et": cands[i].close_time, "i": i}
        else:
            if s is not None and closes[i] > s:
                trades.append({"net": NOTIONAL * (closes[i] - pos["pe"]) / pos["pe"] - NOTIONAL * rt,
                               "et": pos["et"]})
                pos = None
    return trades


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
W365, W180, W90 = latest - 365 * DAY, latest - 180 * DAY, latest - 90 * DAY


def allt(buy, exsma, hold, rt=0.004):
    out = []
    for cands in data.values():
        out += run(cands, buy, exsma, hold, rt)
    return out


print("=== A) PLATEAU de parametres (net EUR : tout | 365j | 180j | 90j) — RT=0.4% ===")
print(f"{'buy/exitSMA/hold':<22}{'tout':>16}{'365j':>16}{'180j':>16}{'90j':>16}")
for buy in (30, 35, 40):
    for exsma in (8, 10, 12):
        for hold in (10, 15, 20):
            t = allt(buy, exsma, hold)
            cells = []
            for ws in (0, W365, W180, W90):
                a = agg(t, ws)
                cells.append(f"{a['net']:+.0f}(PF{a['pf']:.2f})" if a else "-")
            print(f"buy{buy} sma{exsma} h{hold:<6}" + "".join(f"{c:>16}" for c in cells))

print()
print("=== B) PERF PAR ACTIF (config buy35/sma10/h15) — net EUR : tout | 365j ===")
for s, cands in data.items():
    t = run(cands, 35, 10, 15, 0.004)
    a_all, a_365 = agg(t, 0), agg(t, W365)
    aa = f"{a_all['net']:+.0f} n{a_all['n']} PF{a_all['pf']:.2f}" if a_all else "-"
    a3 = f"{a_365['net']:+.0f} n{a_365['n']} PF{a_365['pf']:.2f}" if a_365 else "-"
    print(f"{s:<8}{aa:>26}{a3:>26}")

print()
print("=== C) SENSIBILITE AUX COUTS (config buy35/sma10/h15) ===")
print(f"{'RT cost':<12}{'tout':>20}{'365j':>20}{'180j':>20}")
for rt in (0.002, 0.004, 0.006):
    t = allt(35, 10, 15, rt)
    cells = []
    for ws in (0, W365, W180):
        a = agg(t, ws)
        cells.append(f"{a['net']:+.0f} PF{a['pf']:.2f}" if a else "-")
    print(f"{rt*100:.1f}% AR    " + "".join(f"{c:>20}" for c in cells))
