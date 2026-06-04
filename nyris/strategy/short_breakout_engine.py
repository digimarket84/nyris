"""Moteur SHORT « cassure de support » (pur, déterministe) — V4.

Règles (toutes mesurables sur klines) :
  - contexte non-haussier (filtre 1h calculé par le runner, `context_bearish`) ;
  - cassure de support confirmée : close < plus_bas(support_lookback) ;
  - volume vendeur en hausse : volume > vol_factor × volume_moyen(vol_lookback) ;
  - stop AU-DESSUS du dernier sommet local (plus_haut(support_lookback)), plafonné ;
  - sortie : take-profit (reward_r×risque) OU trailing stop ATR OU contexte redevenu haussier.
    Pas de sortie sur durée.

Le trailing est exprimé via `Decision.stop` renvoyé sur les holds : le runner persiste
le nouveau stop s'il est plus bas. Aucune dépendance baseline ; aucun effet de bord.
"""

from __future__ import annotations

from decimal import Decimal

from nyris.strategy.indicators import atr
from nyris.strategy.models import Action, Candle, Decision, PositionState, Snapshot
from nyris.strategy.short_models import ShortParams, ShortReason


def breakout_warmup(params: ShortParams) -> int:
    return max(params.support_lookback, params.vol_lookback, params.atr_period) + 2


def _d(v: float | None) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def _price(v: float) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.00000001"))


def evaluate_breakout(
    candles: list[Candle],
    position: PositionState | None,
    params: ShortParams,
    *,
    context_bearish: bool,
    context_value: float | None = None,
) -> Decision:
    n = len(candles)
    if n < breakout_warmup(params):
        last = candles[-1]
        snap = Snapshot(last.close_time, last.close, None, None, _d(context_value), None)
        return Decision(Action.skip, ShortReason.skip_no_data, snap)

    closes = [float(c.close) for c in candles]
    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]
    vols = [float(c.volume) for c in candles]

    at = atr(highs, lows, closes, params.atr_period)
    i = n - 1
    last = candles[i]
    close = closes[i]

    # fenêtres EXCLUANT la bougie courante
    sl = params.support_lookback
    support = min(lows[i - sl:i])
    swing_high = max(highs[i - sl:i])
    avg_vol = sum(vols[i - params.vol_lookback:i]) / params.vol_lookback

    # journalisation : support->ema_fast, swing_high->ema_slow, contexte->ema_trend
    snap = Snapshot(
        last.close_time, last.close, _d(support), _d(swing_high), _d(context_value), _d(at[i])
    )
    if at[i] is None:
        return Decision(Action.skip, ShortReason.skip_no_data, snap)

    if position is None:
        if not context_bearish:
            return Decision(Action.hold, ShortReason.hold_no_downtrend, snap)
        breakdown = close < support
        vol_ok = avg_vol > 0 and vols[i] > params.vol_factor * avg_vol
        if not (breakdown and vol_ok):
            return Decision(Action.hold, ShortReason.hold_no_setup, snap)
        # stop au-dessus du dernier sommet local, plafonné par max_stop_pct
        stop_f = swing_high * (1.0 + params.swing_buffer_pct)
        max_stop = close * (1.0 + params.max_stop_pct)
        if stop_f > max_stop:
            stop_f = max_stop
        if stop_f <= close:  # sécurité : le stop doit être au-dessus de l'entrée
            stop_f = close * 1.002
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
    if not context_bearish:
        return Decision(Action.exit, ShortReason.exit_short_trend_recovered, snap)
    # trailing stop : on resserre le stop vers le bas (jamais vers le haut)
    trail = close + params.trail_atr_mult * at[i]
    new_stop = min(stop, trail)
    return Decision(Action.hold, ShortReason.hold_in_position, snap, stop=_price(new_stop))
