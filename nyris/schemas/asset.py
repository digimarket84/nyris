"""Schémas Pydantic pour les actifs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from nyris.models.asset import AssetStatus


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    display_name: str
    exchange_symbol: str
    quote_currency: str
    status: AssetStatus
    is_tradeable: bool
    notes: str | None
    binance_symbol: str | None
    binance_status: str | None
    market_synced_at: datetime | None
