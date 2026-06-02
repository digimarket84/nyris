"""Schémas Pydantic pour l'agrégation du portefeuille simulé."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class TradeCounts(BaseModel):
    total: int
    draft: int
    open: int
    closed: int
    cancelled: int


class RealizedStats(BaseModel):
    invested: Decimal
    exit_value: Decimal
    pnl_net: Decimal
    pnl_percent: Decimal | None


class OpenExposure(BaseModel):
    invested: Decimal
    trades: int


class AssetStat(BaseModel):
    asset_id: int
    symbol: str
    display_name: str
    closed_trades: int
    invested: Decimal
    exit_value: Decimal
    pnl_net: Decimal
    pnl_percent: Decimal | None


class AssetRef(BaseModel):
    symbol: str
    pnl_net: Decimal
    pnl_percent: Decimal | None


class PortfolioSummary(BaseModel):
    currency: str
    counts: TradeCounts
    realized: RealizedStats
    open_exposure: OpenExposure
    by_asset: list[AssetStat]
    best_asset: AssetRef | None
    worst_asset: AssetRef | None
