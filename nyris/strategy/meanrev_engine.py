"""Moteur MEAN-REVERSION daily pur (RSI survendu, long-only).

Entrée : RSI(14) < rsi_buy (creux survendu). Sortie : close > SMA(exit_sma)
(rebond) OU durée >= max_hold_days. Aucun effet de bord. Bougies daily closes.
"""

from __future__ import annotations

from decimal import Decimal

from nyris.strategy.indicators import rsi as rsi_ind
from nyris.strategy.indicators import sma as sma_ind
from nyris.strategy.meanrev_models import MeanRevDecision, MeanRevParams, MeanRevReason
from nyris.strategy.models import Candle


def warmup(p: MeanRevParams) -> int:
    return max(p.rsi_period + 1, p.exit_sma) + 2


def evaluate_meanrev(
    candles: list[Candle], has_position: bool, bars_held: int, params: MeanRevParams
) -> MeanRevDecision:
    n = len(candles)
    last = candles[-1]
    if n < warmup(params):
        return MeanRevDecision("skip", MeanRevReason.skip_no_data, last.close_time, last.close)
    closes = [float(c.close) for c in candles]
    i = n - 1
    rsi_val = rsi_ind(closes, params.rsi_period)[i]
    sma_val = sma_ind(closes, params.exit_sma)[i]
    if rsi_val is None or sma_val is None:
        return MeanRevDecision("skip", MeanRevReason.skip_no_data, last.close_time, last.close)

    def d(v: float) -> Decimal:
        return Decimal(str(v))

    r, s = d(rsi_val), d(sma_val)
    close = float(last.close)

    if not has_position:
        if rsi_val < params.rsi_buy:
            return MeanRevDecision("enter", MeanRevReason.enter_oversold, last.close_time,
                                   last.close, r, s, entry=last.close)
        return MeanRevDecision("hold", MeanRevReason.hold_flat, last.close_time, last.close, r, s)

    # en position : durée max prioritaire, puis rebond
    if bars_held >= params.max_hold_days:
        return MeanRevDecision("exit", MeanRevReason.exit_max_hold, last.close_time,
                               last.close, r, s)
    if close > sma_val:
        return MeanRevDecision("exit", MeanRevReason.exit_recovered, last.close_time,
                               last.close, r, s)
    return MeanRevDecision("hold", MeanRevReason.hold_in_position, last.close_time,
                           last.close, r, s)
