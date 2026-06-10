"""Reco conseil #1 : FILTRE FUNDING sur l'edge MR-long (VALIDATION echantillon complet).
Thèse : acheter les creux survendus PAIE MIEUX quand le funding n'est pas en euphorie.
Pagination funding AVANT (startTime) -> ~2 ans/alt. Buckets + filtre + fenetres. Lecture seule."""
import json, urllib.request, datetime as dt
from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.services import candles as cs
from sqlalchemy import select

PERP = {"LINK": "LINKUSDT", "AVAX": "AVAXUSDT", "NEAR": "NEARUSDT", "DOGE": "DOGEUSDT",
        "SUI": "SUIUSDT", "PEPE": "1000PEPEUSDT", "ZEC": "ZECUSDT", "WLD": "WLDUSDT",
        "ENA": "ENAUSDT", "POND": "PONDUSDT", "BABY": "BABYUSDT", "HOME": "HOMEUSDT", "LA": "LAUSDT"}
TARGET = 2700
RT = 0.004
DAY = 86_400_000
db = SessionLocal()


def fetch_funding(perp, days=900, pages=10):
    now = int(dt.datetime.now(dt.UTC).timestamp() * 1000)
    start = now - days * DAY
    out = []
    for _ in range(pages):
        u = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={perp}&startTime={start}&limit=1000"
        try:
            r = json.loads(urllib.request.urlopen(u, timeout=25).read())
        except Exception:
            break
        if not r:
            break
        out += r
        nxt = int(r[-1]["fundingTime"]) + 1
        if nxt <= start or len(r) < 2:
            break
        start = nxt
    return out


def daily_funding(perp):
    byday = {}
    for x in fetch_funding(perp):
        d = int(x["fundingTime"]) // DAY * DAY
        byday.setdefault(d, []).append(float(x["fundingRate"]))
    return {d: sum(v) / len(v) for d, v in byday.items()}


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


def mr_trades(cands, fund):
    closes = [float(c.close) for c in cands]
    r14 = rsi_series(closes, 14)
    out, pos = [], None
    for i in range(len(cands)):
        ct = cands[i].close_time
        d0 = ct // DAY * DAY
        if pos is not None and (i - pos["i"]) >= 20:
            out.append((closes[i] / pos["p"] - 1 - RT, pos["f"], pos["ct"])); pos = None
        r = r14[i]
        if r is None:
            continue
        if pos is None:
            if r < 35:
                fs = [fund[d0 - k * DAY] for k in range(0, 3) if (d0 - k * DAY) in fund]
                if not fs:
                    continue
                pos = {"p": closes[i], "i": i, "f": sum(fs) / len(fs), "ct": ct}
        else:
            s = sma(closes, i, 10)
            if s is not None and closes[i] > s:
                out.append((closes[i] / pos["p"] - 1 - RT, pos["f"], pos["ct"])); pos = None
    return out


alltr = []
print("fetch funding (startTime, ~2 ans) + replay MR...")
for s in PERP:
    a = db.scalar(select(Asset).where(Asset.symbol == s))
    if not a or not a.binance_symbol:
        continue
    fund = daily_funding(PERP[s])
    if not fund:
        print("  no funding", s); continue
    cands = cs.get_candles_paginated(a.binance_symbol, "1d", TARGET)
    tr = mr_trades(cands, fund)
    alltr += tr
    print(f"  {s:<6} {len(tr)} trades MR (funding {dt.datetime.fromtimestamp(min(fund)/1000, dt.UTC).date()}->)")

latest = max(t[2] for t in alltr)


def stats(ts, lbl):
    if not ts:
        print(f"  {lbl:<30} 0 trade"); return
    nets = [t[0] * 100 for t in ts]
    gp = sum(x for x in nets if x > 0); gl = -sum(x for x in nets if x < 0)
    print(f"  {lbl:<30} n={len(ts):<4} win={100*sum(1 for x in nets if x>0)/len(ts):3.0f}% "
          f"net={sum(nets):+7.1f}%  moy={sum(nets)/len(ts):+5.2f}%  PF={gp/gl if gl else 999:.2f}")


def block(ts, title):
    print(f"\n=== {title} (n={len(ts)}) ===")
    if len(ts) < 6:
        print("  echantillon trop faible"); return
    fs = sorted(t[1] for t in ts)
    q1 = fs[len(fs) // 3]; q2 = fs[2 * len(fs) // 3]; med = fs[len(fs) // 2]
    stats(ts, "TOUS (non filtre)")
    stats([t for t in ts if t[1] <= q1], "funding BAS (calme/negatif)")
    stats([t for t in ts if q1 < t[1] <= q2], "funding MOYEN")
    stats([t for t in ts if t[1] > q2], "funding HAUT (euphorie)")
    stats([t for t in ts if t[1] <= med], ">>> FILTRE (funding<=median)")


block(alltr, "TOUT l'historique funding")
block([t for t in alltr if t[2] >= latest - 365 * DAY], "365 derniers jours")
block([t for t in alltr if t[2] >= latest - 180 * DAY], "180 derniers jours")
