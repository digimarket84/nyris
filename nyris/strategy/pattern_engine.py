"""Moteur PATTERN pur et déterministe (bidirectionnel).

Schémas (sur `timeframe`) :
  1) Cassure de range (Donchian) : close > plus_haut(N) -> LONG ; close < plus_bas(N) -> SHORT.
  2) Pullback EMA (continuation) : en uptrend (close>EMA_trend), repli sur EMA_pullback puis
     rebond -> LONG ; en downtrend, rejet de EMA_pullback -> SHORT.
La cassure est prioritaire sur le pullback. Stop = ATR (plafonné), TP = reward_r × risque.
Sorties : stop / take-profit selon le sens. Aucun effet de bord.
"""

from __future__ import annotations

from decimal import Decimal

from nyris.strategy.indicators import atr, ema
from nyris.strategy.models import Action, Candle, Snapshot
from nyris.strategy.pattern_models import (
    PatternDecision,
    PatternParams,
    PatternPosition,
    PatternReason,
)


def warmup(p: PatternParams) -> int:
    return max(p.donchian_lookback, p.ema_trend, p.ema_pullback, p.atr_period) + 2


def _d(v: float | None) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def _price(v: float) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.00000001"))


def _long_levels(close: float, a: float, p: PatternParams):
    stop = close - p.atr_stop_mult * a
    floor = close * (1.0 - p.max_stop_pct)
    stop = max(stop, floor)
    if stop >= close:
        stop = close * 0.998
    risk = close - stop
    tp = close + p.reward_r * risk
    return _price(stop), _price(tp)


def _short_levels(close: float, a: float, p: PatternParams):
    stop = close + p.atr_stop_mult * a
    cap = close * (1.0 + p.max_stop_pct)
    stop = min(stop, cap)
    if stop <= close:
        stop = close * 1.002
    risk = stop - close
    tp = max(close - p.reward_r * risk, 0.0)
    return _price(stop), _price(tp)


def evaluate(
    candles: list[Candle], position: PatternPosition | None, params: PatternParams
) -> PatternDecision:
    n = len(candles)
    if n < warmup(params):
        last = candles[-1]
        return PatternDecision(Action.skip, PatternReason.skip_no_data,
                               Snapshot(last.close_time, last.close, None, None, None, None))

    closes = [float(c.close) for c in candles]
    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]
    opens = [float(c.open) for c in candles]
    et = ema(closes, params.ema_trend)
    ep = ema(closes, params.ema_pullback)
    at = atr(highs, lows, closes, params.atr_period)

    i = n - 1
    last = candles[i]
    close = closes[i]
    snap = Snapshot(last.close_time, last.close, _d(ep[i]), None, _d(et[i]), _d(at[i]))
    if et[i] is None or ep[i] is None or at[i] is None:
        return PatternDecision(Action.skip, PatternReason.skip_no_data, snap)

    if position is not None:
        side = position.side
        stop, tp = float(position.stop), float(position.take_profit)
        hit_stop = (close <= stop) if side == "long" else (close >= stop)
        hit_tp = (close >= tp) if side == "long" else (close <= tp)
        if hit_stop:
            return PatternDecision(Action.exit, PatternReason.exit_stop, snap, side=side)
        if hit_tp:
            return PatternDecision(Action.exit, PatternReason.exit_take_profit, snap, side=side)
        return PatternDecision(Action.hold, PatternReason.hold_in_position, snap, side=side)

    # pas de position : recherche d'un schéma
    nlb = params.donchian_lookback
    dch = max(highs[i - nlb:i])  # plus haut des N précédentes (exclut la courante)
    dcl = min(lows[i - nlb:i])
    a = at[i]

    def enter(side, pattern, reason):
        stop, tp = (_long_levels(close, a, params) if side == "long"
                    else _short_levels(close, a, params))
        return PatternDecision(Action.enter, reason, snap, side=side, pattern=pattern,
                               entry=last.close, stop=stop, take_profit=tp)

    # 1) cassure de range (prioritaire)
    if close > dch:
        return enter("long", "donchian", PatternReason.enter_long_breakout)
    if close < dcl:
        return enter("short", "donchian", PatternReason.enter_short_breakdown)

    # 2) pullback EMA (continuation)
    up, down = close > et[i], close < et[i]
    long_pb = up and lows[i] <= ep[i] and close > ep[i] and close > opens[i]
    short_pb = down and highs[i] >= ep[i] and close < ep[i] and close < opens[i]
    if long_pb:
        return enter("long", "pullback", PatternReason.enter_long_pullback)
    if short_pb:
        return enter("short", "pullback", PatternReason.enter_short_pullback)

    return PatternDecision(Action.hold, PatternReason.hold_no_pattern, snap)
