"""PnL pur bidirectionnel (long ET short), net de coûts. Réutilise les arrondis de services.pnl."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from nyris.services.pnl import round_money, round_pct, round_qty


@dataclass(frozen=True)
class EntryResult:
    quantity: Decimal
    entry_cost: Decimal


@dataclass(frozen=True)
class CloseResult:
    exit_cost: Decimal
    funding_cost: Decimal
    pnl_gross: Decimal
    pnl_net: Decimal
    pnl_percent: Decimal


def _per_side_rate(params) -> Decimal:
    return params.commission_rate + params.spread_rate / 2 + params.slippage_rate


def compute_entry(notional: Decimal, entry_price: Decimal, params) -> EntryResult:
    if notional <= 0 or entry_price <= 0:
        raise ValueError("notional et entry_price doivent être > 0")
    quantity = round_qty(notional / entry_price)
    entry_cost = round_money(notional * _per_side_rate(params))
    return EntryResult(quantity=quantity, entry_cost=entry_cost)


def compute_close(
    side: str,
    notional: Decimal,
    quantity: Decimal,
    entry_cost: Decimal,
    exit_price: Decimal,
    params,
    hold_hours: float,
) -> CloseResult:
    if exit_price <= 0 or notional <= 0:
        raise ValueError("exit_price et notional doivent être > 0")
    exit_value = round_money(quantity * exit_price)
    exit_cost = round_money(exit_value * _per_side_rate(params))
    funding_cost = round_money(notional * params.funding_rate_daily * Decimal(str(hold_hours / 24)))
    if side == "long":
        pnl_gross = round_money(exit_value - notional)  # acheté puis revendu
    else:  # short : vendu notional puis racheté
        pnl_gross = round_money(notional - exit_value)
    pnl_net = pnl_gross - entry_cost - exit_cost - funding_cost
    pnl_percent = round_pct(pnl_net / notional * Decimal(100))
    return CloseResult(exit_cost, funding_cost, pnl_gross, pnl_net, pnl_percent)
