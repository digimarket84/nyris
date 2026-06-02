"""Tests unitaires du calcul des frais et du PnL (purs, sans DB)."""

from decimal import Decimal

from nyris.services import pnl


def test_compute_entry_applique_les_frais_et_reduit_la_quantite():
    r = pnl.compute_entry(Decimal("1000"), Decimal("100"), Decimal("0.001"))
    assert r.entry_fee_amount == Decimal("1.00")
    # net investi = 999 -> quantité = 9.99
    assert r.quantity == Decimal("9.990000000000")


def test_compute_close_profit_net_de_frais():
    r = pnl.compute_close(Decimal("1000"), Decimal("9.99"), Decimal("150"), Decimal("0.001"))
    assert r.exit_gross_value == Decimal("1498.50")
    assert r.exit_fee_amount == Decimal("1.50")  # 1.4985 -> HALF_UP
    assert r.exit_net_value == Decimal("1497.00")
    assert r.pnl_net == Decimal("497.00")
    assert r.pnl_percent == Decimal("49.7000")


def test_compute_close_perte():
    r = pnl.compute_close(Decimal("1000"), Decimal("9.99"), Decimal("90"), Decimal("0.001"))
    assert r.exit_gross_value == Decimal("899.10")
    assert r.exit_fee_amount == Decimal("0.90")  # 0.8991 -> HALF_UP
    assert r.exit_net_value == Decimal("898.20")
    assert r.pnl_net == Decimal("-101.80")


def test_compute_entry_prix_invalide():
    import pytest

    with pytest.raises(ValueError):
        pnl.compute_entry(Decimal("1000"), Decimal("0"), Decimal("0.001"))
