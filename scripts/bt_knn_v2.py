"""kNN analogues v2 : PCA (dim reduite) + bibliotheque GLISSANTE recente + cible EXCEDENT/base.
Attaque les 2 causes d'echec v1 (malediction dimension + non-stationnarite). Lecture seule.

Setup causal correct :
- features 24h H1 (idem v1), forward 1/4/12/24h
- scaler + PCA cales sur les 60% les plus ANCIENS (jamais le futur)
- pour chaque point test : voisins cherches dans la fenetre RECENTE glissante
  [t-LIB_BARS, t-embargo] (donc recence + causalite)
- base_local = rendement forward moyen de cette fenetre glissante (le vrai 'hasard' du moment)
- metrique honnete : LIFT = rendement conditionne - base_local (l'edge doit etre > couts)
"""
import numpy as np
from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.services import candles as cs
from sqlalchemy import select

ASSETS = ["BTC", "SOL", "LINK", "AVAX", "DOGE", "PEPE"]
W = 24
HORIZONS = [1, 4, 12, 24]
TARGET = 20000
COST = 0.0025
LIB_BARS = 2880          # ~120 jours de bibliotheque glissante
EMBARGO = 24
STRIDE = 6
db = SessionLocal()


def feats(o, h, l, c, v, i):
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
    last_body = abs(C[-1] - O[-1])
    hammer = 1.0 if (O[-1] - L[-1]) > 2 * last_body and C[-1] > O[-1] else 0.0
    engulf = 1.0 if (C[-1] > O[-1] and C[-2] < O[-2] and C[-1] > O[-2] and O[-1] < C[-2]) else 0.0
    return [ret24, vol, atr_rel, dist_sma, slope, bull_ratio, body, uwick,
            lwick, pos, np.log(vratio), accel, sbreak, max(hammer, engulf)]


def build(sym):
    a = db.scalar(select(Asset).where(Asset.symbol == sym))
    cnd = cs.get_candles_paginated(a.binance_symbol, "1h", TARGET)
    o = np.array([float(x.open) for x in cnd]); h = np.array([float(x.high) for x in cnd])
    lo = np.array([float(x.low) for x in cnd]); c = np.array([float(x.close) for x in cnd])
    v = np.array([float(x.volume) for x in cnd])
    X, Y = [], []
    hmax = max(HORIZONS)
    for i in range(W, len(c) - hmax):
        X.append(feats(o, h, lo, c, v, i))
        Y.append([(c[i + hz] - c[i]) / c[i] for hz in HORIZONS])
    return np.array(X), np.array(Y)


def fit_pca(Xtr, k):
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    Z = (Xtr - mu) / sd
    _, _, Vt = np.linalg.svd(Z, full_matrices=False)
    comp = Vt[:k]
    return mu, sd, comp


def transform(X, mu, sd, comp):
    return ((X - mu) / sd) @ comp.T


CACHE = {s: build(s) for s in ASSETS}


def run_asset(sym, k, N, thr):
    X, Y = CACHE[sym]
    n = len(X)
    split = int(n * 0.60)
    mu, sd, comp = fit_pca(X[:split], k)
    P = transform(X, mu, sd, comp)
    out = {hz: {"base": [], "buy_real": [], "buy_base": []} for hz in HORIZONS}
    for ti in range(max(split, LIB_BARS + EMBARGO), n, STRIDE):
        a0 = ti - LIB_BARS
        a1 = ti - EMBARGO
        lib = P[a0:a1]
        z = P[ti]
        d = np.sqrt(((lib - z) ** 2).sum(1))
        nn = np.argpartition(d, N)[:N]
        for hi, hz in enumerate(HORIZONS):
            fwd = Y[a0:a1][nn, hi]
            base_local = Y[a0:a1, hi].mean()
            real = Y[ti, hi]
            out[hz]["base"].append(real)
            p_up = (fwd > 0).mean()
            exp = fwd.mean()
            # cible EXCEDENT : l'analogue doit promettre de battre le base local au-dela des couts
            if p_up > thr and (exp - base_local) > COST:
                out[hz]["buy_real"].append(real)
                out[hz]["buy_base"].append(base_local)
    return out


def cat(res, hz, key):
    v = []
    for r in res:
        v += r[hz][key]
    return np.array(v)


print(f"kNN v2 (PCA + lib glissante {LIB_BARS}h + cible excedent) | {ASSETS}\n")
for k in (4, 6):
    for N in (50, 100):
        for thr in (0.58,):
            res = [run_asset(s, k, N, thr) for s in ASSETS]
            print(f"### PCA={k} comp, N={N} voisins, seuil P>{thr} ###")
            print(f"{'horizon':<9}{'BUY n':>8}{'BUY %win':>10}{'BUY real':>11}"
                  f"{'base faced':>12}{'LIFT brut':>11}{'net(-cout)':>12}")
            for hz in HORIZONS:
                br = cat(res, hz, "buy_real")
                bb = cat(res, hz, "buy_base")
                if len(br) > 5:
                    lift = br.mean() - bb.mean()
                    print(f"{hz:>3}h     {len(br):>8}{100*(br>0).mean():>9.1f}%"
                          f"{br.mean()*100:>10.2f}%{bb.mean()*100:>11.2f}%"
                          f"{lift*100:>10.2f}%{(br.mean()-COST)*100:>11.2f}%")
                else:
                    print(f"{hz:>3}h     {len(br):>8}{'(trop peu)':>33}")
            print()
