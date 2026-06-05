"""Tests PnL bidirectionnel (long & short)."""

from decimal import Decimal

from nyris.strategy import pattern_pnl
from nyris.strategy.pattern_models import PatternParams

P = PatternParams()


def test_entry():
    r = pattern_pnl.compute_entry(Decimal("25"), Decimal("100"), P)
    assert r.quantity == Decimal("0.25")
    assert r.entry_cost == Decimal("0.04")  # 25 * 0.00175 = 0.04375 -> 0.04


def test_close_long_win():
    r = pattern_pnl.compute_close("long", Decimal("25"), Decimal("0.25"), Decimal("0.04"),
                                  Decimal("110"), P, hold_hours=1.0)
    assert r.pnl_gross == Decimal("2.50")  # (110-100)*0.25
    assert r.pnl_net > 0


def test_close_short_win():
    r = pattern_pnl.compute_close("short", Decimal("25"), Decimal("0.25"), Decimal("0.04"),
                                  Decimal("90"), P, hold_hours=1.0)
    assert r.pnl_gross == Decimal("2.50")  # 25 - 0.25*90
    assert r.pnl_net > 0


def test_close_short_loss():
    r = pattern_pnl.compute_close("short", Decimal("25"), Decimal("0.25"), Decimal("0.04"),
                                  Decimal("110"), P, hold_hours=1.0)
    assert r.pnl_gross == Decimal("-2.50")
    assert r.pnl_net < 0
