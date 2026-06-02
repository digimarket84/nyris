"""Tests des indicateurs purs EMA / ATR."""

from nyris.strategy.indicators import atr, ema, true_range


def test_ema_known_values():
    # period 3 sur [1,2,3,4,5] : seed=2 (SMA), k=0.5
    out = ema([1, 2, 3, 4, 5], 3)
    assert out[0] is None
    assert out[1] is None
    assert out[2] == 2.0
    assert out[3] == 3.0
    assert out[4] == 4.0


def test_ema_insuffisant():
    assert ema([1, 2], 5) == [None, None]


def test_true_range():
    assert true_range(12, 8, 10) == 4  # max(4, 2, 2)
    assert true_range(12, 11, 5) == 7  # gap haussier : |12-5|


def test_atr_constant_moves():
    # high=low=close -> TR = |close - close_prec| = 1 partout, ATR = 1
    closes = [10, 11, 12, 13, 14]
    out = atr(closes, closes, closes, 2)
    assert out[0] is None and out[1] is None
    assert out[2] == 1.0
    assert out[3] == 1.0
    assert out[4] == 1.0
