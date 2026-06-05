"""Tests du moteur SHORT « cassure de support » (V4, pur)."""

from dataclasses import replace
from decimal import Decimal

from nyris.strategy.models import Action, Candle, PositionState
from nyris.strategy.short_breakout_engine import evaluate_breakout
from nyris.strategy.short_models import ShortParams, ShortReason

STEP = 15 * 60 * 1000
Pb = ShortParams(
    strategy="breakdown", support_lookback=5, vol_lookback=5, vol_factor=1.2,
    atr_period=3, trail_atr_mult=2.0, max_stop_pct=0.5, swing_buffer_pct=0.0,
)


def bk(closes, vols=None):
    vols = vols or [1.0] * len(closes)
    out = []
    for i, c in enumerate(closes):
        cd = Decimal(str(c))
        t = STEP * i
        out.append(Candle(t, t + STEP, cd, cd + 1, cd - 1, cd, Decimal(str(vols[i]))))
    return out


# closes : 7 bougies à 100 puis cassure à 95 ; volume du dernier bar = 5 (vs moyenne 1)
BREAK = [100, 100, 100, 100, 100, 100, 100, 95]
VOL_UP = [1, 1, 1, 1, 1, 1, 1, 5]


def test_enter_on_confirmed_breakdown():
    d = evaluate_breakout(bk(BREAK, VOL_UP), None, Pb, context_bearish=True, context_value=120.0)
    assert d.action == Action.enter and d.reason == ShortReason.enter_short_signal
    assert d.stop > d.entry > d.take_profit  # stop au-dessus du sommet, TP en-dessous


def test_no_enter_without_volume():
    d = evaluate_breakout(bk(BREAK, [1] * 8), None, Pb, context_bearish=True, context_value=120.0)
    assert d.action == Action.hold and d.reason == ShortReason.hold_no_setup


def test_no_enter_without_breakdown():
    # dernier close = 100, au-dessus du support (99) -> pas de cassure
    d = evaluate_breakout(bk([100] * 8, VOL_UP), None, Pb, context_bearish=True, context_value=120.0)
    assert d.action == Action.hold and d.reason == ShortReason.hold_no_setup


def test_no_enter_if_context_not_bearish():
    d = evaluate_breakout(bk(BREAK, VOL_UP), None, Pb, context_bearish=False, context_value=120.0)
    assert d.action == Action.hold and d.reason == ShortReason.hold_no_downtrend


def test_exit_stop():
    pos = PositionState(Decimal("95"), Decimal("96"), Decimal("80"), 1)
    d = evaluate_breakout(bk([100] * 8), pos, Pb, context_bearish=True, context_value=120.0)
    assert d.action == Action.exit and d.reason == ShortReason.exit_short_stop


def test_exit_take_profit():
    pos = PositionState(Decimal("95"), Decimal("200"), Decimal("105"), 1)
    d = evaluate_breakout(bk([100] * 8), pos, Pb, context_bearish=True, context_value=120.0)
    assert d.action == Action.exit and d.reason == ShortReason.exit_short_take_profit


def test_exit_trend_recovered():
    pos = PositionState(Decimal("95"), Decimal("200"), Decimal("0"), 1)
    d = evaluate_breakout(bk([100] * 8), pos, Pb, context_bearish=False, context_value=80.0)
    assert d.action == Action.exit and d.reason == ShortReason.exit_short_trend_recovered


def test_trailing_tightens_stop():
    # stop initial très haut ; en position et baissier -> hold avec stop resserré vers le bas
    pos = PositionState(Decimal("95"), Decimal("200"), Decimal("0"), 1)
    d = evaluate_breakout(bk([100] * 8), pos, Pb, context_bearish=True, context_value=120.0)
    assert d.action == Action.hold and d.reason == ShortReason.hold_in_position
    assert d.stop is not None and d.stop < Decimal("200")  # trailing a resserré


def test_breakeven_locks_at_entry():
    # le code breakeven reste paramétrique (désactivé par défaut) : on l'active ici
    p = replace(Pb, breakeven_trigger_pct=0.008)
    # entrée 100, prix favorable à 99 (-1% > seuil 0.8%) -> stop verrouillé au breakeven (100)
    pos = PositionState(Decimal("100"), Decimal("200"), Decimal("0"), 1)
    d = evaluate_breakout(bk([100] * 7 + [99]), pos, p, context_bearish=True, context_value=120.0)
    assert d.action == Action.hold and d.reason == ShortReason.hold_in_position
    assert d.stop == Decimal("100")  # breakeven : plus aucune perte possible
