"""Moteur SHORT pur et déterministe : failed pullback / rejet en tendance baissière.

Deux modes, même fonction (rétro-compatible) :
  - mono-timeframe (legacy) : `evaluate_short(candles, position, params)`
    -> la tendance est jugée par l'EMA `ema_trend` calculée sur `candles`.
  - multi-timeframe (V2)    : `evaluate_short(..., context_bearish=..., context_value=...)`
    -> la tendance vient d'un timeframe supérieur (calculée par le runner) ;
       `candles` ne sert plus qu'au signal d'exécution 1m.

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
    """Chauffe legacy (mono-timeframe, inclut ema_trend)."""
    return max(params.ema_trend, params.ema_pullback, params.atr_period) + 2


def exec_warmup(params: ShortParams) -> int:
    """Chauffe d'exécution (MTF) : seuls les indicateurs du timeframe 1m comptent."""
    return max(params.ema_pullback, params.atr_period) + 2


def _d(v: float | None) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def _price(v: float) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.00000001"))


def evaluate_short(
    candles: list[Candle],
    position: PositionState | None,
    params: ShortParams,
    *,
    context_bearish: bool | None = None,
    context_value: float | None = None,
) -> Decision:
    use_ctx = context_bearish is not None
    need = exec_warmup(params) if use_ctx else warmup(params)

    n = len(candles)
    if n < need:
        last = candles[-1]
        snap = Snapshot(last.close_time, last.close, None, None, _d(context_value), None)
        return Decision(Action.skip, ShortReason.skip_no_data, snap)

    closes = [float(c.close) for c in candles]
    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]
    opens = [float(c.open) for c in candles]

    ep = ema(closes, params.ema_pullback)
    at = atr(highs, lows, closes, params.atr_period)
    et = None if use_ctx else ema(closes, params.ema_trend)

    i = n - 1
    last = candles[i]
    # valeur de tendance affichée dans strategy_decisions (ema_trend) :
    #   - MTF  : EMA du timeframe supérieur (contexte),
    #   - legacy: EMA ema_trend du timeframe courant.
    trend_val = context_value if use_ctx else et[i]
    # ema_pullback (1m) mappé sur ema_fast pour rester lisible dans le journal
    snap = Snapshot(last.close_time, last.close, _d(ep[i]), None, _d(trend_val), _d(at[i]))

    if ep[i] is None or at[i] is None or trend_val is None:
        return Decision(Action.skip, ShortReason.skip_no_data, snap)

    close = closes[i]
    if use_ctx:
        bearish = context_bearish
        recovered = not context_bearish
    else:
        # legacy : porte d'entrée à `close < et`, sortie stricte à `close > et`
        bearish = close < et[i]
        recovered = close > et[i]

    if position is None:
        if not bearish:
            return Decision(Action.hold, ShortReason.hold_no_downtrend, snap)
        # rejet : mèche au-dessus de l'EMA pullback, clôture dessous, bougie baissière
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
    if recovered:
        return Decision(Action.exit, ShortReason.exit_short_trend_recovered, snap)
    if position.bars_held >= params.max_hold:
        return Decision(Action.exit, ShortReason.exit_short_time, snap)
    return Decision(Action.hold, ShortReason.hold_in_position, snap)
