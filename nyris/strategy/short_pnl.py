"""PnL SHORT pur, net de coûts (spread, slippage, commission, funding).

Réutilise les arrondis de services.pnl (purs) sans le modifier. Short = on vend
`notional` au prix d'entrée, on rachète `quantity` au prix de sortie.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from nyris.services.pnl import round_money, round_pct, round_qty


@dataclass(frozen=True)
class ShortEntryResult:
    quantity: Decimal
    entry_cost: Decimal


@dataclass(frozen=True)
class ShortCloseResult:
    exit_cost: Decimal
    funding_cost: Decimal
    pnl_gross: Decimal
    pnl_net: Decimal
    pnl_percent: Decimal


def _per_side_rate(params) -> Decimal:
    # coût adverse par côté = commission + demi-spread + slippage
    return params.commission_rate + params.spread_rate / 2 + params.slippage_rate


def compute_short_entry(notional: Decimal, entry_price: Decimal, params) -> ShortEntryResult:
    if notional <= 0:
        raise ValueError("notional doit être > 0")
    if entry_price <= 0:
        raise ValueError("entry_price doit être > 0")
    quantity = round_qty(notional / entry_price)
    entry_cost = round_money(notional * _per_side_rate(params))
    return ShortEntryResult(quantity=quantity, entry_cost=entry_cost)


def compute_short_close(
    notional: Decimal,
    quantity: Decimal,
    entry_cost: Decimal,
    exit_price: Decimal,
    params,
    bars_held: int,
    tf_hours: float,
) -> ShortCloseResult:
    if exit_price <= 0:
        raise ValueError("exit_price doit être > 0")
    if notional <= 0:
        raise ValueError("notional doit être > 0")

    buyback_gross = round_money(quantity * exit_price)
    exit_cost = round_money(buyback_gross * _per_side_rate(params))
    holding_days = Decimal(str((bars_held * tf_hours) / 24))
    funding_cost = round_money(notional * params.funding_rate_daily * holding_days)

    pnl_gross = round_money(notional - buyback_gross)  # short : baisse du prix = gain
    pnl_net = pnl_gross - entry_cost - exit_cost - funding_cost
    pnl_percent = round_pct(pnl_net / notional * Decimal(100))
    return ShortCloseResult(
        exit_cost=exit_cost,
        funding_cost=funding_cost,
        pnl_gross=pnl_gross,
        pnl_net=pnl_net,
        pnl_percent=pnl_percent,
    )
