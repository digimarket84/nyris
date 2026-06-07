"""Tests du moteur TREND-FOLLOWING daily (Donchian, long-only)."""

from decimal import Decimal

from nyris.strategy.models import Candle
from nyris.strategy.trend_engine import evaluate_trend
from nyris.strategy.trend_models import TrendParams, TrendReason

P = TrendParams(donchian_entry=10, donchian_exit=5)
STEP = 86_400_000


def mk(closes):
    out = []
    for i, c in enumerate(closes):
        cd = Decimal(str(c))
        t = STEP * i
        out.append(Candle(t, t + STEP, cd, cd + 1, cd - 1, cd, Decimal("1")))
    return out


def test_skip_no_data():
    d = evaluate_trend(mk([100] * 5), False, P)
    assert d.action == "skip" and d.reason == TrendReason.skip_no_data


def test_enter_on_breakout():
    # 12 bougies plates à 100 puis cassure à 110 > plus-haut(10)=101
    d = evaluate_trend(mk([100] * 12 + [110]), False, P)
    assert d.action == "enter" and d.reason == TrendReason.enter_trend_breakout
    assert d.entry == Decimal("110")


def test_hold_flat_no_breakout():
    d = evaluate_trend(mk([100] * 13), False, P)
    assert d.action == "hold" and d.reason == TrendReason.hold_flat


def test_hold_in_position():
    d = evaluate_trend(mk([100] * 13), True, P)
    assert d.action == "hold" and d.reason == TrendReason.hold_in_position


def test_exit_on_down_cross():
    # en position, cassure du plus-bas(5) : derniere bougie à 90 < min(low 5 derniers)=98
    d = evaluate_trend(mk([100] * 12 + [90]), True, P)
    assert d.action == "exit" and d.reason == TrendReason.exit_trend_down
