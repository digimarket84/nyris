"""Moteur SHORT pur et déterministe : failed pullback / rejet en tendance baissière.

Réutilise indicators.ema/atr et les dataclasses Decision/Snapshot/Action. Renvoie
un `Decision` (réutilisable par recorder.build_decision_record). Aucune dépendance
au baseline ; aucun effet de bord.
"""

from __future__ import annotations

from decimal import Decimal

from nyris.strategy.indicators import atr, ema
from nyris.strategy.models import Action, Candle, Decision, PositionState, Snapshot
from nyris.strategy.short_models import ShortParams, ShortReason


def warmup(params: ShortParams) -> int:
    return max(params.ema_trend, params.ema_pullback, params.atr_period) + 2


def _d(v: float | None) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def _price(v: float) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.00000001"))


def evaluate_short(
    candles: list[Candle], position: PositionState | None, params: ShortParams
) -> Decision:
    n = len(candles)
    if n < warmup(params):
        last = candles[-1]
        snap = Snapshot(last.close_time, last.close, None, None, None, None)
        return Decision(Action.skip, ShortReason.skip_no_data, snap)

    closes = [float(c.close) for c in candles]
    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]
    opens = [float(c.open) for c in candles]

    et = ema(closes, params.ema_trend)
    ep = ema(closes, params.ema_pullback)
    at = atr(highs, lows, closes, params.atr_period)

    i = n - 1
    last = candles[i]
    # ema_pullback mappé sur ema_fast pour rester lisible dans strategy_decisions
    snap = Snapshot(last.close_time, last.close, _d(ep[i]), None, _d(et[i]), _d(at[i]))
    if None in (et[i], ep[i], at[i]):
        return Decision(Action.skip, ShortReason.skip_no_data, snap)

    close = closes[i]

    if position is None:
        if close >= et[i]:
            return Decision(Action.hold, ShortReason.hold_no_downtrend, snap)
        rejection = highs[i] >= ep[i] and close < ep[i] and close < opens[i]
        if not rejection:
            return Decision(Action.hold, ShortReason.hold_no_setup, snap)
        # niveaux short : stop AU-DESSUS, take profit EN-DESSOUS
        stop_f = close + params.atr_stop_mult * at[i]
        max_stop = close * (1.0 + params.max_stop_pct)
        if stop_f > max_stop:
            stop_f = max_stop
        risk = stop_f - close
        tp_f = max(close - params.reward_r * risk, 0.0)
        return Decision(
            Action.enter,
            ShortReason.enter_short_signal,
            snap,
            entry=last.close,
            stop=_price(stop_f),
            take_profit=_price(tp_f),
        )

    stop = float(position.stop)
    tp = float(position.take_profit)
    if close >= stop:
        return Decision(Action.exit, ShortReason.exit_short_stop, snap)
    if close <= tp:
        return Decision(Action.exit, ShortReason.exit_short_take_profit, snap)
    if close > et[i]:
        return Decision(Action.exit, ShortReason.exit_short_trend_recovered, snap)
    if position.bars_held >= params.max_hold:
        return Decision(Action.exit, ShortReason.exit_short_time, snap)
    return Decision(Action.hold, ShortReason.hold_in_position, snap)
