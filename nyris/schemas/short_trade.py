"""Schémas de lecture + filtres des trades SHORT (source de vérité : short_trades)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ShortTradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    symbol: str  # résolu par jointure assets (attribut transient)
    status: str
    side: str
    amount_invested: Decimal  # notional engagé €
    entry_price: Decimal
    exit_price: Decimal | None
    quantity: Decimal
    stop_price: Decimal | None
    take_profit_price: Decimal | None
    entry_cost: Decimal
    exit_cost: Decimal | None
    funding_cost: Decimal | None
    fees_total: Decimal  # entry_cost + exit_cost + funding_cost (transient)
    pnl_gross: Decimal | None
    pnl_net: Decimal | None
    pnl_percent: Decimal | None
    entry_reason: str | None
    exit_reason: str | None
    run_id: str | None
    params_key: str
    opened_at: datetime
    closed_at: datetime | None


class ShortTradeFilters(BaseModel):
    symbol: str | None = None
    status: str | None = None  # open / closed
    run_id: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ShortTradePage(BaseModel):
    items: list[ShortTradeRead]
    total: int
    limit: int
    offset: int


class ShortTradeStats(BaseModel):
    """Agrégats. PnL/frais/win_rate calculés sur les trades CLÔTURÉS (réconciliables)."""

    trades_total: int
    open_count: int
    closed_count: int
    pnl_gross_total: Decimal
    fees_total: Decimal
    pnl_net_total: Decimal
    wins: int
    losses: int
    win_rate: float | None  # None si aucun trade clôturé
