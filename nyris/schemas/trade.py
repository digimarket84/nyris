"""Schémas Pydantic (contrats d'API) pour les trades simulés."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from nyris.models.simulated_trade import TradeStatus

_MAX_RATE = Decimal("0.1")  # garde-fou anti-faute de frappe (10 % max)


class TradeCreate(BaseModel):
    asset_id: int
    amount_invested: Decimal = Field(gt=0, description="Capital brut engagé, en EUR")
    entry_price: Decimal = Field(gt=0, description="Prix d'entrée par unité, en EUR")
    entry_fee_rate: Decimal | None = Field(default=None, ge=0, le=_MAX_RATE)
    fee_model: str | None = None
    fee_currency: str | None = None
    notes: str | None = None


class TradeClose(BaseModel):
    exit_price: Decimal = Field(gt=0, description="Prix de sortie par unité, en EUR")
    exit_fee_rate: Decimal | None = Field(default=None, ge=0, le=_MAX_RATE)


class TradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    status: TradeStatus

    amount_invested: Decimal
    entry_price: Decimal
    quantity: Decimal

    fee_model: str
    fee_currency: str
    entry_fee_rate: Decimal
    entry_fee_amount: Decimal
    exit_fee_rate: Decimal | None
    exit_fee_amount: Decimal | None

    exit_price: Decimal | None
    exit_gross_value: Decimal | None
    exit_net_value: Decimal | None
    pnl_net: Decimal | None
    pnl_percent: Decimal | None

    notes: str | None
    opened_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
