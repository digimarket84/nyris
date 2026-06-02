"""Schéma de lecture des décisions de stratégie (sérialisable)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


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
