"""Schémas Pydantic pour les données de marché (Binance read-only)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class MarketPrice(BaseModel):
    asset_id: int
    symbol: str
    binance_symbol: str
    price: Decimal
    quote_currency: str
    as_of: datetime
    source: str = "binance"


class MarketPrices(BaseModel):
    quote_currency: str
    count: int
    as_of: datetime
    prices: list[MarketPrice]


class AssetMarketStatus(BaseModel):
    symbol: str
    binance_symbol: str | None
    binance_status: str | None


class MarketSyncResult(BaseModel):
    checked: int
    tradable: int
    not_listed: int
    synced_at: datetime
    assets: list[AssetMarketStatus]
