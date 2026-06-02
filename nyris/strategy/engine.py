"""Moteur de décision PUR et déterministe.

`evaluate()` ne dépend que des bougies fournies (clôturées), de l'état de
position et des paramètres. Aucune dépendance à l'heure système. La logique de
décision vit dans `_decide()` (par index, sur indicateurs précalculés) — utilisée
à la fois par `evaluate()` (1 bougie) et par le backtest (précalcul O(n)).
"""

from __future__ import annotations

from decimal import Decimal

from nyris.strategy.indicators import atr, ema
from nyris.strategy.models import (
    Action,
    Candle,
    Decision,
    PositionState,
    Reason,
    Snapshot,
    StrategyParams,
)


def _d(v: float | None) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def _price(v: float) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.00000001"))


def warmup(p: StrategyParams) -> int:
    return max(p.ema_trend, p.ema_slow, p.atr_period) + 2


def _decide(
    i: int,
    ef: list,
    es: list,
    et: list,
    at: list,
    candles: list[Candle],
    position: PositionState | None,
    params: StrategyParams,
) -> Decision:
    last = candles[i]
    snap = Snapshot(
        candle_close_time=last.close_time,
        close=last.close,
        ema_fast=_d(ef[i]),
        ema_slow=_d(es[i]),
        ema_trend=_d(et[i]),
        atr=_d(at[i]),
    )
    if None in (ef[i], es[i], et[i], at[i], ef[i - 1], es[i - 1]):
        return Decision(Action.skip, Reason.no_data, snap)

    close = float(last.close)
    p = params

    if position is None:
        trend_ok = close > et[i]
        cross_up = ef[i - 1] <= es[i - 1] and ef[i] > es[i]
        if not trend_ok:
            return Decision(Action.hold, Reason.flat_no_trend, snap)
        if not cross_up:
            return Decision(Action.hold, Reason.flat_no_cross, snap)
        stop_f = close - p.atr_stop_mult * at[i]
        min_stop = close * (1.0 - p.max_stop_pct)  # risque plafonné
        if stop_f < min_stop:
            stop_f = min_stop
        risk = close - stop_f
        tp_f = close + p.reward_r * risk
        return Decision(
            Action.enter,
            Reason.enter_signal,
            snap,
            entry=last.close,
            stop=_price(stop_f),
            take_profit=_price(tp_f),
        )

    stop = float(position.stop)
    tp = float(position.take_profit)
    if close <= stop:
        return Decision(Action.exit, Reason.exit_stop, snap)
    if close >= tp:
        return Decision(Action.exit, Reason.exit_take_profit, snap)
    cross_down = ef[i - 1] >= es[i - 1] and ef[i] < es[i]
    if cross_down:
        return Decision(Action.exit, Reason.exit_inverse, snap)
    if close < et[i]:
        return Decision(Action.exit, Reason.exit_trend_invalidated, snap)
    if position.bars_held >= p.max_hold:
        return Decision(Action.exit, Reason.exit_time, snap)
    return Decision(Action.hold, Reason.in_position_hold, snap)


def compute_indicators(
    candles: list[Candle], params: StrategyParams
) -> tuple[list, list, list, list]:
    closes = [float(c.close) for c in candles]
    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]
    ef = ema(closes, params.ema_fast)
    es = ema(closes, params.ema_slow)
    et = ema(closes, params.ema_trend)
    at = atr(highs, lows, closes, params.atr_period)
    return ef, es, et, at


def evaluate(
    candles: list[Candle], position: PositionState | None, params: StrategyParams
) -> Decision:
    """Décide pour UN actif, sur la dernière bougie clôturée de `candles`."""
    n = len(candles)
    if n < warmup(params):
        last = candles[-1]
        snap = Snapshot(last.close_time, last.close, None, None, None, None)
        return Decision(Action.skip, Reason.no_data, snap)
    ef, es, et, at = compute_indicators(candles, params)
    return _decide(n - 1, ef, es, et, at, candles, position, params)
