"""Table des trades du runner PATTERN (bidirectionnel long/short, paper-only).

Table SÉPARÉE de simulated_trades (baseline) et short_trades : isolation totale.
`side` = 'long' ou 'short' ; `pattern` = schéma déclencheur ('donchian'/'pullback').
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nyris.models.base import Base, TimestampMixin

_MONEY = Numeric(18, 2)
_PRICE = Numeric(20, 8)
_QTY = Numeric(30, 12)
_RATE = Numeric(10, 6)
_PCT = Numeric(9, 4)


class PatternTrade(Base, TimestampMixin):
    __tablename__ = "pattern_trades"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="open", nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(5), nullable=False)  # long / short
    pattern: Mapped[str | None] = mapped_column(String(20), nullable=True)  # donchian / pullback

    amount_invested: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)  # notional €
    entry_price: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(_QTY, nullable=False)
    stop_price: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)
    take_profit_price: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)

    commission_rate: Mapped[Decimal] = mapped_column(_RATE, nullable=False)
    spread_rate: Mapped[Decimal] = mapped_column(_RATE, nullable=False)
    slippage_rate: Mapped[Decimal] = mapped_column(_RATE, nullable=False)
    funding_rate_daily: Mapped[Decimal] = mapped_column(_RATE, nullable=False)
    entry_cost: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    exit_cost: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    funding_cost: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)

    exit_price: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)
    pnl_gross: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    pnl_net: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    pnl_percent: Mapped[Decimal | None] = mapped_column(_PCT, nullable=True)

    entry_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    params_key: Mapped[str] = mapped_column(String(80), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
