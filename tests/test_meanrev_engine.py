"""Tests du moteur MEAN-REVERSION daily (RSI survendu, long-only)."""

from decimal import Decimal

from nyris.strategy.meanrev_engine import evaluate_meanrev
from nyris.strategy.meanrev_models import MeanRevParams, MeanRevReason
from nyris.strategy.models import Candle

P = MeanRevParams(rsi_period=14, rsi_buy=35.0, exit_sma=10, max_hold_days=20)
STEP = 86_400_000


def mk(closes):
    out = []
    for i, c in enumerate(closes):
        cd = Decimal(str(c))
        t = STEP * i
        out.append(Candle(t, t + STEP, cd, cd + 1, cd - 1, cd, Decimal("1")))
    return out


def test_skip_no_data():
    d = evaluate_meanrev(mk([100] * 5), False, 0, P)
    assert d.action == "skip" and d.reason == MeanRevReason.skip_no_data


def test_enter_when_oversold():
    # 20 bougies hautes puis chute continue -> RSI(14) plonge sous 35
    closes = [100] * 20 + [98, 95, 92, 89, 86, 83, 80, 77]
    d = evaluate_meanrev(mk(closes), False, 0, P)
    assert d.action == "enter" and d.reason == MeanRevReason.enter_oversold
    assert d.entry == Decimal("77")


def test_hold_flat_when_not_oversold():
    d = evaluate_meanrev(mk([100] * 30), False, 0, P)
    assert d.action == "hold" and d.reason == MeanRevReason.hold_flat


def test_exit_on_recovery():
    # en position, close au-dessus de la SMA10 -> rebond -> sortie
    closes = [100] * 20 + [98, 95, 92, 89, 86, 83, 80, 120]
    d = evaluate_meanrev(mk(closes), True, 3, P)
    assert d.action == "exit" and d.reason == MeanRevReason.exit_recovered


def test_exit_on_max_hold():
    # en position, sous la SMA (pas de rebond) mais durée max atteinte -> sortie forcée
    closes = [100] * 20 + [98, 95, 92, 89, 86, 83, 80, 77]
    d = evaluate_meanrev(mk(closes), True, 20, P)
    assert d.action == "exit" and d.reason == MeanRevReason.exit_max_hold


def test_hold_in_position():
    # en position, sous la SMA, durée < max -> on garde
    closes = [100] * 20 + [98, 95, 92, 89, 86, 83, 80, 77]
    d = evaluate_meanrev(mk(closes), True, 3, P)
    assert d.action == "hold" and d.reason == MeanRevReason.hold_in_position
