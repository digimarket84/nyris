"""Schémas Pydantic pour les actifs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    name: str
    quote_currency: str
    is_active: bool
