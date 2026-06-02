"""Schémas Pydantic pour l'agrégation du portefeuille simulé."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class PortfolioFilters(BaseModel):
    """Filtres de query pour l'agrégation (fenêtre sur closed_at)."""

    model_config = ConfigDict(populate_by_name=True)

    from_: AwareDatetime | None = Field(default=None, alias="from")
    to: AwareDatetime | None = None
    asset_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _validate_range(self) -> PortfolioFilters:
        if self.from_ is not None and self.to is not None and self.from_ > self.to:
            raise ValueError("`from` doit être antérieur ou égal à `to`")
        return self


class AppliedPortfolioFilters(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None
    asset_id: int | None = None
    date_field: str = "closed_at"


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
    filters: AppliedPortfolioFilters
    counts: TradeCounts
    realized: RealizedStats
    open_exposure: OpenExposure
    by_asset: list[AssetStat]
    best_asset: AssetRef | None
    worst_asset: AssetRef | None
