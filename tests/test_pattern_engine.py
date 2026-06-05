"""Tests du moteur PATTERN (cassure Donchian + pullback, long & short)."""

from decimal import Decimal

from nyris.strategy.models import Action, Candle
from nyris.strategy.pattern_engine import evaluate
from nyris.strategy.pattern_models import PatternParams, PatternPosition, PatternReason

STEP = 5 * 60 * 1000
P = PatternParams(donchian_lookback=5, ema_trend=5, ema_pullback=3, atr_period=3, max_stop_pct=0.5)
FLAT = (100, 101, 99, 100)  # o,h,l,c


def mk(rows):
    out = []
    for i, (o, h, lo, c) in enumerate(rows):
        t = STEP * i
        out.append(Candle(t, t + STEP, Decimal(str(o)), Decimal(str(h)),
                          Decimal(str(lo)), Decimal(str(c)), Decimal("1")))
    return out


def test_long_breakout():
    d = evaluate(mk([FLAT] * 7 + [(103, 106, 103, 105)]), None, P)
    assert d.action == Action.enter and d.reason == PatternReason.enter_long_breakout
    assert d.side == "long" and d.stop < d.entry < d.take_profit


def test_short_breakdown():
    d = evaluate(mk([FLAT] * 7 + [(97, 97, 94, 95)]), None, P)
    assert d.action == Action.enter and d.reason == PatternReason.enter_short_breakdown
    assert d.side == "short" and d.stop > d.entry > d.take_profit


def test_hold_no_pattern():
    d = evaluate(mk([FLAT] * 8), None, P)
    assert d.action == Action.hold and d.reason == PatternReason.hold_no_pattern


def test_exit_long_stop():
    pos = PatternPosition(side="long", entry=Decimal("100"), stop=Decimal("98"),
                          take_profit=Decimal("120"))
    d = evaluate(mk([FLAT] * 7 + [(97, 98, 96, 97)]), pos, P)
    assert d.action == Action.exit and d.reason == PatternReason.exit_stop


def test_exit_long_take_profit():
    pos = PatternPosition(side="long", entry=Decimal("100"), stop=Decimal("90"),
                          take_profit=Decimal("104"))
    d = evaluate(mk([FLAT] * 7 + [(103, 106, 103, 105)]), pos, P)
    assert d.action == Action.exit and d.reason == PatternReason.exit_take_profit


def test_exit_short_stop():
    pos = PatternPosition(side="short", entry=Decimal("100"), stop=Decimal("103"),
                          take_profit=Decimal("80"))
    d = evaluate(mk([FLAT] * 7 + [(103, 106, 103, 104)]), pos, P)
    assert d.action == Action.exit and d.reason == PatternReason.exit_stop


def test_exit_short_take_profit():
    pos = PatternPosition(side="short", entry=Decimal("100"), stop=Decimal("200"),
                          take_profit=Decimal("96"))
    d = evaluate(mk([FLAT] * 7 + [(97, 97, 94, 95)]), pos, P)
    assert d.action == Action.exit and d.reason == PatternReason.exit_take_profit
