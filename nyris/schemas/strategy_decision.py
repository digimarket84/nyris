"""Schémas de lecture + filtres des décisions de stratégie."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class StrategyDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    evaluated_at: datetime
    asset_id: int
    symbol: str
    timeframe: str
    candle_close_time: int
    close_price: Decimal
    ema_fast: Decimal | None
    ema_slow: Decimal | None
    ema_trend: Decimal | None
    atr: Decimal | None
    action: str
    reason: str
    position_state: str
    entry_price: Decimal | None
    stop_price: Decimal | None
    take_profit_price: Decimal | None
    params_key: str
    run_id: str | None
    simulated_trade_id: int | None
    notes: str | None


class StrategyDecisionFilters(BaseModel):
    """Filtres de query. Dates en ISO 8601 AVEC timezone (naïf -> 422)."""

    model_config = ConfigDict(populate_by_name=True)

    run_id: str | None = None
    asset_id: int | None = Field(default=None, gt=0)
    symbol: str | None = None
    timeframe: str | None = None
    action: str | None = None
    reason: str | None = None
    position_state: str | None = None
    from_: AwareDatetime | None = Field(default=None, alias="from")
    to: AwareDatetime | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_range(self) -> StrategyDecisionFilters:
        if self.from_ is not None and self.to is not None and self.from_ > self.to:
            raise ValueError("`from` doit être antérieur ou égal à `to`")
        return self


class StrategyDecisionPage(BaseModel):
    items: list[StrategyDecisionRead]
    total: int
    limit: int
    offset: int
