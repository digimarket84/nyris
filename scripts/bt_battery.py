"""Batterie de backtests multi-strategies x multi-fenetres (daily). Lecture seule, aucune ecriture DB.

But : trouver une classe de strategie a edge REEL, et surtout voir ce qui marche RECEMMENT
(le crypto evolue). Pour chaque strategie on agrege les trades dont l'ENTREE tombe dans la
fenetre : tout / 365j / 180j / 90j / 30j. Sizing fixe 100 EUR/trade, net de frais.
"""
from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.services import candles as cs
from sqlalchemy import select

UNIVERSE = ["BTC", "ETH", "SOL", "LINK", "AVAX", "NEAR", "DOGE"]
TARGET = 2700
NOTIONAL = 100.0
RT_COST = 0.004          # 0.4% aller-retour
FUNDING_DAY = 0.0001     # charge/j pour les shorts seulement
DAY = 86_400_000

db = SessionLocal()


def load(sym):
    a = db.scalar(select(Asset).where(Asset.symbol == sym))
    if not a or not a.binance_symbol:
        return None
    return cs.get_candles_paginated(a.binance_symbol, "1d", TARGET)


# ---------- indicateurs purs ----------
def sma(arr, i, n):
    return sum(arr[i - n:i]) / n if i >= n else None


def ema_series(arr, n):
    out = [None] * len(arr)
    if len(arr) < n:
        return out
    k = 2 / (n + 1)
    e = sum(arr[:n]) / n
    out[n - 1] = e
    for i in range(n, len(arr)):
        e = arr[i] * k + e * (1 - k)
        out[i] = e
    return out


def rsi_series(arr, n=14):
    out = [None] * len(arr)
    if len(arr) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = arr[i] - arr[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n
    out[n] = 100 - 100 / (1 + (ag / al if al else 1e9))
    for i in range(n + 1, len(arr)):
        d = arr[i] - arr[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100 - 100 / (1 + (ag / al if al else 1e9))
    return out


# ---------- moteur generique ----------
# Une strategie = fonction(ctx, i) -> (want_long: bool) pour les strats "regime/etat"
# ou des signaux d'entree/sortie. On modelise tout en "etat desire" long-only :
#   en cumulant des positions longues quand l'etat est vrai, on entre quand faux->vrai,
#   on sort quand vrai->faux. Simple, robuste, sans look-ahead (indics sur [.. i-1] ou i).

def run_state(cands, want_fn, side="long"):
    """want_fn(ctx, i) -> bool (etat desire en position). Entree/sortie sur cloture i."""
    closes = [float(c.close) for c in cands]
    highs = [float(c.high) for c in cands]
    lows = [float(c.low) for c in cands]
    ctx = {"closes": closes, "highs": highs, "lows": lows,
           "ema": {}, "rsi": rsi_series(closes, 14)}
    trades = []
    pos = None
    n = len(cands)
    for i in range(n):
        want = want_fn(ctx, i)
        if want is None:
            continue
        if pos is None and want:
            pos = {"pe": closes[i], "et": cands[i].close_time}
        elif pos is not None and not want:
            pe, px = pos["pe"], closes[i]
            days = max((cands[i].close_time - pos["et"]) / DAY, 0.0)
            if side == "long":
                gross = NOTIONAL * (px - pe) / pe
                cost = NOTIONAL * RT_COST
            else:
                gross = NOTIONAL * (pe - px) / pe
                cost = NOTIONAL * RT_COST + NOTIONAL * FUNDING_DAY * days
            trades.append({"net": gross - cost, "et": pos["et"],
                           "xt": cands[i].close_time, "days": days})
            pos = None
    return trades


def get_ema(ctx, n):
    if n not in ctx["ema"]:
        ctx["ema"][n] = ema_series(ctx["closes"], n)
    return ctx["ema"][n]


# ---------- definitions de strategies (etat desire long) ----------
def s_donchian(entry, exitn):
    def f(ctx, i):
        if i < max(entry, exitn) + 1:
            return None
        c = ctx["closes"][i]
        up = max(ctx["highs"][i - entry:i])
        lo = min(ctx["lows"][i - exitn:i])
        # etat: on veut etre long si on vient de casser le haut; rester tant que > plus-bas exit
        # approx etat: long si close>plus-haut(entry) OR (close>plus-bas(exit) et deja tendance)
        # -> on encode via 2 seuils en renvoyant un etat hysteresis simule par le moteur:
        return c > up if True else c > lo  # entree sur cassure haute
    # hysteresis correcte: gere via wrapper ci-dessous
    return f


def s_donchian_hyst(entry, exitn):
    """Vrai Donchian: entre si close>haut(entry), sort si close<bas(exit). Hysteresis."""
    state = {"in": False}

    def f(ctx, i):
        if i < max(entry, exitn) + 1:
            return None
        c = ctx["closes"][i]
        up = max(ctx["highs"][i - entry:i])
        lo = min(ctx["lows"][i - exitn:i])
        if not state["in"]:
            if c > up:
                state["in"] = True
        else:
            if c < lo:
                state["in"] = False
        return state["in"]
    return f


def s_sma_regime(n):
    def f(ctx, i):
        m = sma(ctx["closes"], i, n)
        if m is None:
            return None
        return ctx["closes"][i] > m
    return f


def s_ema_cross(fast, slow):
    def f(ctx, i):
        ef, es = get_ema(ctx, fast), get_ema(ctx, slow)
        if ef[i] is None or es[i] is None:
            return None
        return ef[i] > es[i]
    return f


def s_tsmom(lookback):
    def f(ctx, i):
        if i < lookback:
            return None
        return ctx["closes"][i] > ctx["closes"][i - lookback]
    return f


def s_rsi2_meanrev(buy=10, sellrsi=60, trend=200):
    """Connors-style: long si RSI(2)<buy et close>SMA(trend); sort si RSI>sellrsi."""
    rsi2_cache = {}

    def f(ctx, i):
        if "r2" not in rsi2_cache:
            rsi2_cache["r2"] = rsi_series(ctx["closes"], 2)
        r2 = rsi2_cache["r2"][i]
        m = sma(ctx["closes"], i, trend)
        if r2 is None or m is None:
            return None
        c = ctx["closes"][i]
        if c <= m:          # uptrend filter
            return False
        # etat desire: True quand survendu, False quand RSI remonte
        if r2 < buy:
            return True
        if r2 > sellrsi:
            return False
        return None  # zone neutre: laisse l'etat tel quel (moteur garde la position)
    return f


# ---------- fenetres + metriques ----------
def windows(latest):
    return [("tout", 0), ("365j", latest - 365 * DAY), ("180j", latest - 180 * DAY),
            ("90j", latest - 90 * DAY), ("30j", latest - 30 * DAY)]


def maxdd(trades_sorted):
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for t in trades_sorted:
        eq += t["net"]
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return dd


def agg(trades, wstart):
    sel = [t for t in trades if t["et"] >= wstart]
    if not sel:
        return None
    nets = [t["net"] for t in sel]
    gp = sum(x for x in nets if x > 0)
    gl = -sum(x for x in nets if x < 0)
    pf = gp / gl if gl > 0 else 999.0
    wins = sum(1 for x in nets if x > 0)
    sel_sorted = sorted(sel, key=lambda t: t["xt"])
    return {"n": len(sel), "net": sum(nets), "pf": pf,
            "win": 100 * wins / len(sel), "dd": maxdd(sel_sorted)}


def bh_window(data, wstart):
    rets = []
    for cands in data.values():
        sel = [c for c in cands if c.close_time >= wstart]
        if len(sel) >= 2:
            rets.append(100 * (float(sel[-1].close) - float(sel[0].close)) / float(sel[0].close))
    return sum(rets) / len(rets) if rets else None


# ---------- run ----------
data = {}
for s in UNIVERSE:
    c = load(s)
    if c:
        data[s] = c
latest = max(c[-1].close_time for c in data.values())
WINS = windows(latest)

STRATS = [
    ("LONG Donchian 20/10", lambda: s_donchian_hyst(20, 10), "long"),
    ("LONG Donchian 50/20", lambda: s_donchian_hyst(50, 20), "long"),
    ("LONG Donchian 100/50", lambda: s_donchian_hyst(100, 50), "long"),
    ("LONG Donchian 55/20 (turtle)", lambda: s_donchian_hyst(55, 20), "long"),
    ("LONG SMA100 regime", lambda: s_sma_regime(100), "long"),
    ("LONG SMA200 regime", lambda: s_sma_regime(200), "long"),
    ("LONG EMA 20/50 cross", lambda: s_ema_cross(20, 50), "long"),
    ("LONG EMA 50/200 cross", lambda: s_ema_cross(50, 200), "long"),
    ("LONG TSMOM 90j", lambda: s_tsmom(90), "long"),
    ("LONG TSMOM 180j", lambda: s_tsmom(180), "long"),
    ("LONG RSI2 meanrev", lambda: s_rsi2_meanrev(), "long"),
]

print(f"Donnees: {', '.join(f'{k}={len(v)}' for k, v in data.items())}")
print(f"Fenetres (net EUR agrege, sizing 100/trade) | nb actifs={len(data)}\n")
hdr = f"{'Strategie':<32}" + "".join(f"{w[0]:>26}" for w in WINS)
print(hdr)
print("-" * len(hdr))

# B&H reference
bh_row = f"{'(ref) Buy&Hold moy %':<32}"
for _, ws in WINS:
    v = bh_window(data, ws)
    bh_row += f"{(f'{v:+.0f}%' if v is not None else '-'):>26}"
print(bh_row)
print("-" * len(hdr))

for name, builder, side in STRATS:
    alltr = []
    for cands in data.values():
        alltr += run_state(cands, builder(), side)
    row = f"{name:<32}"
    for _, ws in WINS:
        a = agg(alltr, ws)
        if a is None:
            row += f"{'-':>26}"
        else:
            cell = f"{a['net']:+.0f}E n{a['n']} PF{a['pf']:.2f} w{a['win']:.0f}"
            row += f"{cell:>26}"
    print(row)
