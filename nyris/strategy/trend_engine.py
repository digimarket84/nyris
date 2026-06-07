"""Moteur TREND-FOLLOWING daily pur (Donchian, long-only).

Entrée : close > plus_haut(donchian_entry jours précédents). Sortie : close < plus_bas(
donchian_exit jours précédents). Aucun effet de bord. Bougies daily clôturées uniquement.
"""

from __future__ import annotations

from decimal import Decimal

from nyris.strategy.models import Candle
from nyris.strategy.trend_models import TrendDecision, TrendParams, TrendReason


def warmup(p: TrendParams) -> int:
    return max(p.donchian_entry, p.donchian_exit) + 2


def evaluate_trend(
    candles: list[Candle], has_position: bool, params: TrendParams
) -> TrendDecision:
    n = len(candles)
    last = candles[-1]
    if n < warmup(params):
        return TrendDecision("skip", TrendReason.skip_no_data, last.close_time, last.close)
    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]
    close = float(last.close)
    i = n - 1
    dch = max(highs[i - params.donchian_entry:i])  # plus-haut des N jours précédents
    dcl = min(lows[i - params.donchian_exit:i])     # plus-bas des M jours précédents
    d = lambda v: Decimal(str(v))  # noqa: E731

    if not has_position:
        if close > dch:
            return TrendDecision("enter", TrendReason.enter_trend_breakout, last.close_time,
                                 last.close, d(dch), d(dcl), entry=last.close)
        return TrendDecision("hold", TrendReason.hold_flat, last.close_time, last.close,
                             d(dch), d(dcl))

    if close < dcl:
        return TrendDecision("exit", TrendReason.exit_trend_down, last.close_time,
                             last.close, d(dch), d(dcl))
    return TrendDecision("hold", TrendReason.hold_in_position, last.close_time,
                         last.close, d(dch), d(dcl))
