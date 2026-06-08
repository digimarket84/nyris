"""Round 5 : finalisation MR daily sur ALTS volatils (majors retires, negatifs).
Confirme la config, split IS/OOS, drawdown, positions simultanees. Lecture seule."""
from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.services import candles as cs
from sqlalchemy import select

ALTS = ["LINK", "AVAX", "NEAR", "DOGE", "SUI", "PEPE", "ENA", "WLD", "ZEC",
        "POND", "BABY", "HOME", "LA"]
TARGET = 2700
NOTIONAL = 100.0
RT = 0.004
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


def run(cands, buy, exit_sma, hold):
    closes = [float(c.close) for c in cands]
    r14 = rsi_series(closes, 14)
    trades, pos = [], None
    for i in range(len(cands)):
        if pos is not None and (i - pos["i"]) >= hold:
            trades.append({"net": NOTIONAL * (closes[i] - pos["pe"]) / pos["pe"] - NOTIONAL * RT,
                           "et": pos["et"], "xt": cands[i].close_time})
            pos = None
        r = r14[i]
        if r is None:
            continue
        if pos is None:
            if r < buy:
                pos = {"pe": closes[i], "et": cands[i].close_time, "i": i}
        else:
            s = sma(closes, i, exit_sma)
            if s is not None and closes[i] > s:
                trades.append({"net": NOTIONAL * (closes[i] - pos["pe"]) / pos["pe"] - NOTIONAL * RT,
                               "et": pos["et"], "xt": cands[i].close_time})
                pos = None
    return trades


def stats(trades):
    if not trades:
        return None
    nets = [t["net"] for t in trades]
    gp = sum(x for x in nets if x > 0)
    gl = -sum(x for x in nets if x < 0)
    # drawdown sur equity ordonnee par sortie
    eq = peak = dd = 0.0
    for t in sorted(trades, key=lambda x: x["xt"]):
        eq += t["net"]
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {"n": len(trades), "net": sum(nets), "pf": gp / gl if gl else 999.0,
            "win": 100 * sum(1 for x in nets if x > 0) / len(trades), "dd": dd}


def fmt(s):
    return "-" if s is None else f"{s['net']:+.0f}E n{s['n']} PF{s['pf']:.2f} w{s['win']:.0f} DD{s['dd']:.0f}"


data = {s: c for s in ALTS if (c := load(s))}
latest = max(c[-1].close_time for c in data.values())


def windowed(buy, exsma, hold, ws):
    out = []
    for cands in data.values():
        out += [t for t in run(cands, buy, exsma, hold) if t["et"] >= ws]
    return out


print(f"ALTS-only ({len(data)}) | RT=0.4% | sizing 100/trade\n")
for (buy, exsma, hold) in [(35, 10, 20), (35, 12, 20), (30, 10, 20)]:
    print(f"### config buy{buy}/sma{exsma}/hold{hold} ###")
    for name, ws in [("tout", 0), ("365j", latest - 365 * DAY), ("180j", latest - 180 * DAY),
                     ("90j", latest - 90 * DAY), ("30j", latest - 30 * DAY)]:
        print(f"  {name:<6} {fmt(stats(windowed(buy, exsma, hold, ws)))}")
    print()

# IS/OOS : split chronologique 70/30 par actif
print("=== IS/OOS (split 70/30 chrono par actif) — config buy35/sma10/h20 ===")
is_tr, oos_tr = [], []
for cands in data.values():
    cut = cands[int(len(cands) * 0.7)].close_time
    for t in run(cands, 35, 10, 20):
        (is_tr if t["et"] < cut else oos_tr).append(t)
print(f"  IS  {fmt(stats(is_tr))}")
print(f"  OOS {fmt(stats(oos_tr))}")

# positions simultanees max (sur tout l'historique, config buy35/sma10/h20)
print()
print("=== positions simultanees (dimensionnement runner) — buy35/sma10/h20 ===")
events = []
for cands in data.values():
    for t in run(cands, 35, 10, 20):
        events.append((t["et"], +1))
        events.append((t["xt"], -1))
events.sort()
cur = mx = 0
for _, d in events:
    cur += d
    mx = max(mx, cur)
print(f"  max positions simultanees toutes confondues = {mx}")
