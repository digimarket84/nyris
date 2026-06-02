"""Calcul PUR des frais et du PnL (aucune dépendance DB/HTTP).

Toutes les valeurs monétaires sont des Decimal. Les arrondis sont appliqués
aux frontières (argent: 2 déc., quantité: 12 déc., %: 4 déc.) en ROUND_HALF_UP.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

Q_MONEY = Decimal("0.01")
Q_QTY = Decimal("0.000000000001")  # 12 décimales
Q_PCT = Decimal("0.0001")


def round_money(value: Decimal) -> Decimal:
    return value.quantize(Q_MONEY, rounding=ROUND_HALF_UP)


def round_qty(value: Decimal) -> Decimal:
    return value.quantize(Q_QTY, rounding=ROUND_HALF_UP)


def round_pct(value: Decimal) -> Decimal:
    return value.quantize(Q_PCT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class EntryResult:
    entry_fee_amount: Decimal
    quantity: Decimal


@dataclass(frozen=True)
class CloseResult:
    exit_fee_amount: Decimal
    exit_gross_value: Decimal
    exit_net_value: Decimal
    pnl_net: Decimal
    pnl_percent: Decimal


def compute_entry(
    amount_invested: Decimal, entry_price: Decimal, entry_fee_rate: Decimal
) -> EntryResult:
    """Frais d'entrée + quantité réellement achetée (nette de frais)."""
    if amount_invested <= 0:
        raise ValueError("amount_invested doit être > 0")
    if entry_price <= 0:
        raise ValueError("entry_price doit être > 0")

    entry_fee_amount = round_money(amount_invested * entry_fee_rate)
    net_invested = amount_invested - entry_fee_amount
    quantity = round_qty(net_invested / entry_price)
    return EntryResult(entry_fee_amount=entry_fee_amount, quantity=quantity)


def compute_close(
    amount_invested: Decimal,
    quantity: Decimal,
    exit_price: Decimal,
    exit_fee_rate: Decimal,
) -> CloseResult:
    """Valeur de sortie nette de frais + PnL net (vs capital brut engagé)."""
    if exit_price <= 0:
        raise ValueError("exit_price doit être > 0")
    if amount_invested <= 0:
        raise ValueError("amount_invested doit être > 0")

    exit_gross_value = round_money(quantity * exit_price)
    exit_fee_amount = round_money(exit_gross_value * exit_fee_rate)
    exit_net_value = exit_gross_value - exit_fee_amount
    pnl_net = exit_net_value - amount_invested
    pnl_percent = round_pct(pnl_net / amount_invested * Decimal(100))
    return CloseResult(
        exit_fee_amount=exit_fee_amount,
        exit_gross_value=exit_gross_value,
        exit_net_value=exit_net_value,
        pnl_net=pnl_net,
        pnl_percent=pnl_percent,
    )
