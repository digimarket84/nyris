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
