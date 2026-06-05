"""Schémas de lecture + filtres des trades PATTERN (bidirectionnel ; table pattern_trades)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PatternTradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    symbol: str  # jointure assets (transient)
    status: str
    side: str  # long / short
    pattern: str | None
    amount_invested: Decimal
    entry_price: Decimal
    exit_price: Decimal | None
    quantity: Decimal
    stop_price: Decimal | None
    take_profit_price: Decimal | None
    entry_cost: Decimal
    exit_cost: Decimal | None
    funding_cost: Decimal | None
    fees_total: Decimal  # transient
    pnl_gross: Decimal | None
    pnl_net: Decimal | None
    pnl_percent: Decimal | None
    entry_reason: str | None
    exit_reason: str | None
    run_id: str | None
    params_key: str
    opened_at: datetime
    closed_at: datetime | None


class PatternTradeFilters(BaseModel):
    symbol: str | None = None
    status: str | None = None
    side: str | None = None
    pattern: str | None = None
    run_id: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class PatternTradePage(BaseModel):
    items: list[PatternTradeRead]
    total: int
    limit: int
    offset: int


class PatternTradeStats(BaseModel):
    """Agrégats sur les trades CLÔTURÉS, avec ventilation long/short."""

    trades_total: int
    open_count: int
    closed_count: int
    pnl_gross_total: Decimal
    fees_total: Decimal
    pnl_net_total: Decimal
    wins: int
    losses: int
    win_rate: float | None
    long_count: int
    long_net: Decimal
    short_count: int
    short_net: Decimal
