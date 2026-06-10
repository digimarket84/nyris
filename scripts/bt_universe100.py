"""Univers elargi : top ~100 paires USDT liquides (>2M$/j) par volume 24h, hors stablecoins/leveraged.
Backtest meanrev (RSI14<35, exit close>SMA10 ou 20j) sur 30/60/90 jours. La question : ~100 actifs
donnent-ils assez de trades en 30j pour juger en RECENT, et l'edge tient-il ? Lecture seule."""
import json, urllib.request
from nyris.services import candles as cs

RT = 0.004
DAY = 86_400_000
MIN_VOL = 2_000_000          # plancher liquidite 24h
TOPN = 100
STABLES = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "AEUR", "EUR", "EURI",
           "USD1", "XUSD", "GUSD", "PYUSD", "USDE"}


def universe():
    t = json.loads(urllib.request.urlopen(
        "https://api.binance.com/api/v3/ticker/24hr", timeout=30).read())
    cand = []
    for x in t:
        s = x["symbol"]
        if not s.endswith("USDT"):
            continue
        base = s[:-4]
        if base in STABLES:
            continue
        if any(s.endswith(suf + "USDT") for suf in ("UP", "DOWN", "BULL", "BEAR")):
            continue
        qv = float(x["quoteVolume"])
        if qv >= MIN_VOL:
            cand.append((s, qv))
    cand.sort(key=lambda z: -z[1])
    return [s for s, _ in cand[:TOPN]]


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


def mr_trades(cands, sym):
    closes = [float(c.close) for c in cands]
    r14 = rsi_series(closes, 14)
    out, pos = [], None
    for i in range(len(cands)):
        if pos is not None and (i - pos["i"]) >= 20:
            out.append((pos["ct"], closes[i] / pos["p"] - 1 - RT, sym)); pos = None
        r = r14[i]
        if r is None:
            continue
        if pos is None:
            if r < 35:
                pos = {"p": closes[i], "i": i, "ct": cands[i].close_time}
        else:
            s = sma(closes, i, 10)
            if s is not None and closes[i] > s:
                out.append((pos["ct"], closes[i] / pos["p"] - 1 - RT, sym)); pos = None
    return out


syms = universe()
print(f"univers = {len(syms)} paires USDT >{MIN_VOL/1e6:.0f}M$/j")
alltr = []
ok = 0
for s in syms:
    try:
        c = cs.get_candles(s, "1d", 150)
        if len(c) < 40:
            continue
        alltr += mr_trades(c, s)
        ok += 1
    except Exception:
        pass
latest = max(t[0] for t in alltr)
print(f"actifs avec historique suffisant : {ok} | trades MR totaux (150j) : {len(alltr)}\n")


def stats(ws_days):
    ws = latest - ws_days * DAY
    sel = [t for t in alltr if t[0] >= ws]
    if not sel:
        print(f"  {ws_days}j : 0 trade"); return
    nets = [t[1] * 100 for t in sel]
    gp = sum(x for x in nets if x > 0); gl = -sum(x for x in nets if x < 0)
    assets = len(set(t[2] for t in sel))
    print(f"  {ws_days:>3}j : n={len(sel):<4} ({assets} actifs)  win={100*sum(1 for x in nets if x>0)/len(sel):3.0f}%  "
          f"net={sum(nets):+7.1f}%  moy={sum(nets)/len(sel):+5.2f}%  PF={gp/gl if gl else 999:.2f}")


print("=== meanrev (RSI14<35) sur univers elargi, par fenetre recente ===")
for w in (7, 14, 30, 60, 90):
    stats(w)
print("\n(net = somme des rendements %, sizing fixe ; juge = PF>1 et assez de trades)")
