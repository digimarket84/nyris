"""Indicateurs purs et déterministes : EMA et ATR (Wilder).

Travaillent sur des listes de float (mêmes entrées -> mêmes sorties). Les
fonctions renvoient une liste alignée sur l'entrée, avec None pendant la
période de chauffe.
"""

from __future__ import annotations


def ema(values: list[float], period: int) -> list[float | None]:
    n = len(values)
    out: list[float | None] = [None] * n
    if period <= 0 or n < period:
        return out
    # amorçage = SMA des `period` premières valeurs
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    k = 2.0 / (period + 1)
    prev = seed
    for i in range(period, n):
        prev = values[i] * k + prev * (1.0 - k)
        out[i] = prev
    return out


def true_range(high: float, low: float, prev_close: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def atr(
    highs: list[float], lows: list[float], closes: list[float], period: int
) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if period <= 0 or n < period + 1:
        return out
    trs: list[float] = [0.0]  # index 0 sans TR (pas de close précédent)
    for i in range(1, n):
        trs.append(true_range(highs[i], lows[i], closes[i - 1]))
    # premier ATR = moyenne simple des `period` premiers TR (index 1..period)
    first = sum(trs[1 : period + 1]) / period
    out[period] = first
    prev = first
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + trs[i]) / period  # lissage de Wilder
        out[i] = prev
    return out


def sma(values: list[float], period: int) -> list[float | None]:
    n = len(values)
    out: list[float | None] = [None] * n
    for i in range(period - 1, n):
        out[i] = sum(values[i - period + 1 : i + 1]) / period
    return out


def rsi(values: list[float], period: int) -> list[float | None]:
    """RSI de Wilder. Période courte (ex. 2) supportée."""
    n = len(values)
    out: list[float | None] = [None] * n
    if n < period + 1:
        return out
    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        ch = values[i] - values[i - 1]
        gains[i] = max(ch, 0.0)
        losses[i] = max(-ch, 0.0)
    ag = sum(gains[1 : period + 1]) / period
    al = sum(losses[1 : period + 1]) / period
    out[period] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(period + 1, n):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def bollinger(
    values: list[float], period: int, mult: float
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Renvoie (mid, upper, lower). Écart-type population (÷period)."""
    n = len(values)
    mid: list[float | None] = [None] * n
    up: list[float | None] = [None] * n
    lo: list[float | None] = [None] * n
    for i in range(period - 1, n):
        w = values[i - period + 1 : i + 1]
        m = sum(w) / period
        sd = (sum((x - m) ** 2 for x in w) / period) ** 0.5
        mid[i], up[i], lo[i] = m, m + mult * sd, m - mult * sd
    return mid, up, lo


def adx(
    highs: list[float], lows: list[float], closes: list[float], period: int
) -> list[float | None]:
    """ADX de Wilder (DMI). None pendant la chauffe (premier ADX à 2*period)."""
    n = len(closes)
    out: list[float | None] = [None] * n
    if n < 2 * period + 1:
        return out
    pdm = [0.0] * n
    mdm = [0.0] * n
    tr = [0.0] * n
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
        tr[i] = true_range(highs[i], lows[i], closes[i - 1])
    atr_s = sum(tr[1 : period + 1])
    ps = sum(pdm[1 : period + 1])
    ms = sum(mdm[1 : period + 1])
    dx: list[float | None] = [None] * n

    def _dx(a: float, pp: float, mm: float) -> float:
        if a == 0:
            return 0.0
        pdi = 100 * pp / a
        mdi = 100 * mm / a
        return 0.0 if (pdi + mdi) == 0 else 100 * abs(pdi - mdi) / (pdi + mdi)

    dx[period] = _dx(atr_s, ps, ms)
    for i in range(period + 1, n):
        atr_s += tr[i] - atr_s / period
        ps += pdm[i] - ps / period
        ms += mdm[i] - ms / period
        dx[i] = _dx(atr_s, ps, ms)
    av = sum(dx[period + 1 : 2 * period + 1]) / period
    out[2 * period] = av
    for i in range(2 * period + 1, n):
        av = (av * (period - 1) + dx[i]) / period
        out[i] = av
    return out


def donchian(
    highs: list[float], lows: list[float], period: int
) -> tuple[list[float | None], list[float | None]]:
    """Canaux de Donchian : (plus_haut, plus_bas) des `period` bougies PRÉCÉDENTES (exclut i)."""
    n = len(highs)
    up: list[float | None] = [None] * n
    lo: list[float | None] = [None] * n
    for i in range(period, n):
        up[i] = max(highs[i - period : i])
        lo[i] = min(lows[i - period : i])
    return up, lo
