"""Schémas de filtrage et d'historique paginé des trades simulés."""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from nyris.models.simulated_trade import TradeStatus
from nyris.schemas.trade import TradeRead


class HistoryDateField(enum.StrEnum):
    opened_at = "opened_at"
    closed_at = "closed_at"
    created_at = "created_at"


class HistorySort(enum.StrEnum):
    opened_at_desc = "opened_at:desc"
    opened_at_asc = "opened_at:asc"
    closed_at_desc = "closed_at:desc"
    closed_at_asc = "closed_at:asc"
    pnl_net_desc = "pnl_net:desc"
    pnl_net_asc = "pnl_net:asc"
    id_desc = "id:desc"
    id_asc = "id:asc"


class TradeHistoryFilters(BaseModel):
    """Filtres de query pour l'historique. Dates en ISO 8601 AVEC timezone."""

    model_config = ConfigDict(populate_by_name=True)

    from_: AwareDatetime | None = Field(default=None, alias="from")
    to: AwareDatetime | None = None
    asset_id: int | None = Field(default=None, gt=0)
    status: TradeStatus | None = None
    date_field: HistoryDateField = HistoryDateField.opened_at
    sort: HistorySort = HistorySort.opened_at_desc
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_range(self) -> TradeHistoryFilters:
        if self.from_ is not None and self.to is not None and self.from_ > self.to:
            raise ValueError("`from` doit être antérieur ou égal à `to`")
        return self


class Pagination(BaseModel):
    total: int
    limit: int
    offset: int
    returned: int
    has_more: bool


class AppliedHistoryFilters(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None
    asset_id: int | None = None
    status: TradeStatus | None = None
    date_field: HistoryDateField
    sort: HistorySort


class TradeHistoryPage(BaseModel):
    items: list[TradeRead]
    pagination: Pagination
    filters: AppliedHistoryFilters
