"""Tests du moteur SHORT pur — mode legacy (mono-TF) et mode MTF (contexte injecté)."""

from dataclasses import replace
from decimal import Decimal

from nyris.strategy.indicators import ema
from nyris.strategy.models import Action, Candle, PositionState
from nyris.strategy.short_engine import evaluate_short
from nyris.strategy.short_models import ShortParams, ShortReason

STEP = 4 * 3600 * 1000
# legacy : ema_trend petit pour rester mono-TF ; MTF : ema_trend ignoré
P = ShortParams(ema_trend=5, ema_pullback=3, atr_period=3, max_hold=5)


def mk(closes):
    out = []
    for i, c in enumerate(closes):
        cd = Decimal(str(c))
        t = STEP * i
        out.append(Candle(open_time=t, close_time=t + STEP, open=cd, high=cd + 1, low=cd - 1,
                          close=cd, volume=Decimal("1")))
    return out


def rejection_candles():
    """Suite baissière dont la dernière bougie est un rejet de l'EMA pullback."""
    closes = [120, 118, 116, 114, 112, 110, 108, 106, 104, 102, 100]
    ep = ema([float(x) for x in closes], P.ema_pullback)
    candles = mk(closes)
    i = len(closes) - 1
    candles[-1] = replace(
        candles[-1], high=Decimal(str(ep[i] + 5)), open=candles[-1].close + Decimal("3")
    )
    return candles


# ---------- mode legacy (mono-timeframe) ----------
def test_no_data():
    d = evaluate_short(mk([100, 101, 102]), None, P)
    assert d.action == Action.skip and d.reason == ShortReason.skip_no_data


def test_hold_no_downtrend():
    d = evaluate_short(mk([100, 101, 102, 103, 104, 105, 106, 107, 108]), None, P)
    assert d.action == Action.hold and d.reason == ShortReason.hold_no_downtrend


def test_enter_short_on_failed_pullback():
    d = evaluate_short(rejection_candles(), None, P)
    assert d.action == Action.enter and d.reason == ShortReason.enter_short_signal
    assert d.stop > d.entry > d.take_profit  # short : stop au-dessus, TP en-dessous


def test_exit_short_stop():
    pos = PositionState(Decimal("100"), Decimal("95"), Decimal("10"), 1)
    d = evaluate_short(mk([100] * 12), pos, P)
    assert d.action == Action.exit and d.reason == ShortReason.exit_short_stop


def test_exit_short_take_profit():
    pos = PositionState(Decimal("100"), Decimal("200"), Decimal("105"), 1)
    d = evaluate_short(mk([100] * 12), pos, P)
    assert d.action == Action.exit and d.reason == ShortReason.exit_short_take_profit


def test_exit_short_trend_recovered_legacy():
    pos = PositionState(Decimal("100"), Decimal("1e9"), Decimal("0"), 1)
    d = evaluate_short(mk([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110]), pos, P)
    assert d.action == Action.exit and d.reason == ShortReason.exit_short_trend_recovered


def test_exit_short_time():
    pos = PositionState(Decimal("100"), Decimal("1e9"), Decimal("0"), P.max_hold)
    d = evaluate_short(mk([100] * 12), pos, P)
    assert d.action == Action.exit and d.reason == ShortReason.exit_short_time


def test_hold_in_position():
    pos = PositionState(Decimal("100"), Decimal("1e9"), Decimal("0"), 1)
    d = evaluate_short(mk([100] * 12), pos, P)
    assert d.action == Action.hold and d.reason == ShortReason.hold_in_position


# ---------- mode MTF (contexte injecté par le runner) ----------
def test_mtf_enter_when_context_bearish():
    d = evaluate_short(rejection_candles(), None, P, context_bearish=True, context_value=130.0)
    assert d.action == Action.enter and d.reason == ShortReason.enter_short_signal
    assert d.stop > d.entry > d.take_profit
    assert d.snapshot.ema_trend == Decimal("130.0")  # contexte 1h journalisé


def test_mtf_hold_when_context_not_bearish():
    # même setup de rejet, mais contexte haussier -> pas d'entrée
    d = evaluate_short(rejection_candles(), None, P, context_bearish=False, context_value=130.0)
    assert d.action == Action.hold and d.reason == ShortReason.hold_no_downtrend


def test_mtf_exit_when_context_recovered():
    pos = PositionState(Decimal("100"), Decimal("1e9"), Decimal("0"), 1)
    d = evaluate_short(mk([100] * 12), pos, P, context_bearish=False, context_value=90.0)
    assert d.action == Action.exit and d.reason == ShortReason.exit_short_trend_recovered


def test_mtf_hold_in_position_when_still_bearish():
    pos = PositionState(Decimal("100"), Decimal("1e9"), Decimal("0"), 1)
    d = evaluate_short(mk([100] * 12), pos, P, context_bearish=True, context_value=130.0)
    assert d.action == Action.hold and d.reason == ShortReason.hold_in_position
