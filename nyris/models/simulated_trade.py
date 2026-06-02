"""Table des trades simulés (paper trading) avec frais figés entrée/sortie."""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nyris.models.base import Base, TimestampMixin


class TradeStatus(enum.StrEnum):
    draft = "draft"
    open = "open"
    closed = "closed"
    cancelled = "cancelled"


# Précisions décimales (cohérentes avec les arrondis du service PnL)
_MONEY = Numeric(18, 2)
_PRICE = Numeric(20, 8)
_QTY = Numeric(30, 12)
_RATE = Numeric(10, 6)
_PCT = Numeric(9, 4)


class SimulatedTrade(Base, TimestampMixin):
    __tablename__ = "simulated_trades"
    __table_args__ = (
        # Accélère l'agrégation par actif/statut
        Index("ix_simulated_trades_asset_status", "asset_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True, nullable=False)
    status: Mapped[TradeStatus] = mapped_column(
        SAEnum(TradeStatus, name="trade_status"),
        default=TradeStatus.open,
        nullable=False,
        index=True,
    )

    # --- Entrée (saisie + calculé) ---
    amount_invested: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(_QTY, nullable=False)

    # --- Frais (figés sur le trade pour la traçabilité) ---
    fee_model: Mapped[str] = mapped_column(String(30), default="flat_rate", nullable=False)
    fee_currency: Mapped[str] = mapped_column(String(10), default="EUR", nullable=False)
    entry_fee_rate: Mapped[Decimal] = mapped_column(_RATE, nullable=False)
    entry_fee_amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    exit_fee_rate: Mapped[Decimal | None] = mapped_column(_RATE, nullable=True)
    exit_fee_amount: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)

    # --- Sortie / résultat (calculé à la fermeture) ---
    exit_price: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)
    exit_gross_value: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    exit_net_value: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    pnl_net: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    pnl_percent: Mapped[Decimal | None] = mapped_column(_PCT, nullable=True)

    # --- Métadonnées (opened_at/closed_at indexés pour les filtres période) ---
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    asset: Mapped["Asset"] = relationship(back_populates="trades")  # noqa: F821, UP037
