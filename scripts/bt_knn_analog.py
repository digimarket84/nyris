"""Backtest stategie ANALOGUES / kNN sur configuration 24h (H1). Lecture seule.

Methodo anti-overfit :
- features causales (fenetre 24 bougies H1 closes), forward returns 1/4/12/24h
- split chrono 70/30 : bibliotheque = train (passe), decisions = test (OOS futur)
- embargo : on retire les derniers points du train pour eviter le chevauchement
  de l'horizon forward avec le test
- standardisation (z-score) calee sur le TRAIN uniquement
- metrique honnete : rendement conditionne (signal) vs TAUX DE BASE inconditionnel
"""
import numpy as np
from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.services import candles as cs
from sqlalchemy import select

ASSETS = ["BTC", "SOL", "LINK", "AVAX", "DOGE", "PEPE"]
W = 24                       # fenetre H1
HORIZONS = [1, 4, 12, 24]
TARGET = 20000
COST_RT = 0.0025             # 0.25% aller-retour (directionnel, frais+spread)
db = SessionLocal()


def feats(o, h, l, c, v, i):
    """Vecteur de features pour la fenetre [i-W, i) ; decision a la cloture i-1."""
    O, H, L, C, V = o[i - W:i], h[i - W:i], l[i - W:i], c[i - W:i], v[i - W:i]
    ret24 = (C[-1] - C[0]) / C[0]
    lr = np.diff(np.log(C))
    vol = lr.std()
    tr = np.maximum(H[1:] - L[1:], np.maximum(np.abs(H[1:] - C[:-1]), np.abs(L[1:] - C[:-1])))
    atr_rel = tr.mean() / C[-1]
    sma20 = C.mean()
    dist_sma = (C[-1] - sma20) / sma20
    slope = (C[12:].mean() - C[:12].mean()) / C[:12].mean()
    bull_ratio = (C > O).mean()
    body = (np.abs(C - O) / O).mean()
    uwick = ((H - np.maximum(O, C)) / O).mean()
    lwick = ((np.minimum(O, C) - L) / O).mean()
    rng = H.max() - L.min()
    pos = (C[-1] - L.min()) / rng if rng > 0 else 0.5
    vratio = V[12:].mean() / V[:12].mean() if V[:12].mean() > 0 else 1.0
    accel = (C[-1] - C[12]) / C[12] - (C[12] - C[0]) / C[0]
    sbreak = 1.0 if C[-1] > H[:-1].max() else 0.0
    # pattern bougie : marteau haussier (longue meche basse) ou englobante haussiere
    last_body = abs(C[-1] - O[-1])
    hammer = 1.0 if (O[-1] - L[-1]) > 2 * last_body and C[-1] > O[-1] else 0.0
    engulf = 1.0 if (C[-1] > O[-1] and C[-2] < O[-2]
                     and C[-1] > O[-2] and O[-1] < C[-2]) else 0.0
    patt = max(hammer, engulf)
    return [ret24, vol, atr_rel, dist_sma, slope, bull_ratio, body, uwick,
            lwick, pos, np.log(vratio), accel, sbreak, patt]


def build(sym):
    a = db.scalar(select(Asset).where(Asset.symbol == sym))
    cnd = cs.get_candles_paginated(a.binance_symbol, "1h", TARGET)
    o = np.array([float(x.open) for x in cnd])
    h = np.array([float(x.high) for x in cnd])
    lo = np.array([float(x.low) for x in cnd])
    c = np.array([float(x.close) for x in cnd])
    v = np.array([float(x.volume) for x in cnd])
    X, Y, idx = [], [], []
    hmax = max(HORIZONS)
    for i in range(W, len(c) - hmax):
        X.append(feats(o, h, lo, c, v, i))
        Y.append([(c[i + hz] - c[i]) / c[i] for hz in HORIZONS])
        idx.append(i)
    return np.array(X), np.array(Y), np.array(idx)


def run_asset(sym, N, thr, stride=4):
    X, Y, idx = build(sym)
    n = len(X)
    split = int(n * 0.70)
    embargo = 24
    tr_end = split - embargo
    Xtr, Ytr = X[:tr_end], Y[:tr_end]
    # standardisation calee sur le train
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    Ztr = (Xtr - mu) / sd
    res = {hz: {"base": [], "buy": [], "buy_pred": [], "sell": []} for hz in HORIZONS}
    test_ids = range(split, n, stride)
    for ti in test_ids:
        z = (X[ti] - mu) / sd
        d = np.sqrt(((Ztr - z) ** 2).sum(1))
        nn = np.argpartition(d, N)[:N]
        for hi, hz in enumerate(HORIZONS):
            fwd = Ytr[nn, hi]
            real = Y[ti, hi]
            res[hz]["base"].append(real)
            p_up = (fwd > 0).mean()
            exp = fwd.mean()
            if p_up > thr and exp - COST_RT > 0:
                res[hz]["buy"].append(real - COST_RT)
                res[hz]["buy_pred"].append(exp)
            elif p_up < (1 - thr) and exp + COST_RT < 0:
                res[hz]["sell"].append(-real - COST_RT)
    return res


def agg(all_res, hz, key):
    vals = []
    for r in all_res:
        vals += r[hz][key]
    return np.array(vals)


print(f"kNN analogues | actifs={ASSETS} | N voisins, seuil testes\n")
for N in (50, 100):
    for thr in (0.58, 0.62):
        all_res = [run_asset(s, N, thr) for s in ASSETS]
        print(f"### N={N} voisins, seuil P>{thr} ###")
        print(f"{'horizon':<9}{'BASE %up':>10}{'BASE moy':>10}"
              f"{'BUY n':>8}{'BUY %win':>10}{'BUY moy net':>13}{'LIFT vs base':>14}")
        for hz in HORIZONS:
            base = agg(all_res, hz, "base")
            buy = agg(all_res, hz, "buy")
            base_up = 100 * (base > 0).mean()
            base_mean = base.mean()
            if len(buy) > 0:
                buy_win = 100 * (buy > 0).mean()
                buy_mean = buy.mean()
                lift = buy_mean - base_mean  # net vs base brut (conservateur)
                print(f"{hz:>3}h     {base_up:>10.1f}{base_mean*100:>9.2f}%"
                      f"{len(buy):>8}{buy_win:>9.1f}%{buy_mean*100:>12.2f}%{lift*100:>13.2f}%")
            else:
                print(f"{hz:>3}h     {base_up:>10.1f}{base_mean*100:>9.2f}%{0:>8}"
                      f"{'-':>10}{'-':>13}{'-':>14}")
        print()
