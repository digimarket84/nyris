"""Table des trades SHORT simulés (runner challenger short, paper-only).

Table SÉPARÉE de `simulated_trades` : garantit qu'aucune requête du runner
baseline (qui lit `simulated_trades`) ne capte un short. Aucune dépendance ni
modification du baseline.
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


class ShortTrade(Base, TimestampMixin):
    __tablename__ = "short_trades"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="open", nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(5), default="short", nullable=False)

    # Entrée (vente à découvert simulée)
    amount_invested: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)  # notional engagé €
    entry_price: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(_QTY, nullable=False)
    stop_price: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)
    take_profit_price: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)

    # Coûts (taux figés + montants)
    commission_rate: Mapped[Decimal] = mapped_column(_RATE, nullable=False)
    spread_rate: Mapped[Decimal] = mapped_column(_RATE, nullable=False)
    slippage_rate: Mapped[Decimal] = mapped_column(_RATE, nullable=False)
    funding_rate_daily: Mapped[Decimal] = mapped_column(_RATE, nullable=False)
    entry_cost: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    exit_cost: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    funding_cost: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)

    # Sortie / résultat (rachat)
    exit_price: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)
    pnl_gross: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    pnl_net: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    pnl_percent: Mapped[Decimal | None] = mapped_column(_PCT, nullable=True)

    # Traçabilité / isolation
    run_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    params_key: Mapped[str] = mapped_column(String(80), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
