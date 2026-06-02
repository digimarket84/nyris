"""Table des actifs suivis (watchlist).

Distinction importante :
- ``symbol``          : ticker canonique utilisé par Nyris (ex. ATH, RENDER)
- ``exchange_symbol`` : symbole côté exchange (peut différer selon la plateforme)
- ``status``          : cycle de vie de suivi (active / watch_only / delisted)
- ``is_tradeable``    : autorise ou non l'ouverture de trades simulés
- ``binance_symbol``  : paire Binance Spot EUR (ex. BTCEUR) ; null si indisponible
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nyris.models.base import Base, TimestampMixin


class AssetStatus(enum.StrEnum):
    active = "active"
    watch_only = "watch_only"
    delisted = "delisted"


class Asset(Base, TimestampMixin):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    exchange_symbol: Mapped[str] = mapped_column(String(40), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(10), default="EUR", nullable=False)
    status: Mapped[AssetStatus] = mapped_column(
        SAEnum(AssetStatus, name="asset_status"),
        default=AssetStatus.active,
        nullable=False,
        index=True,
    )
    is_tradeable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Métadonnées Binance (alimentées par /market/sync) ---
    binance_symbol: Mapped[str | None] = mapped_column(String(30), nullable=True)
    binance_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    market_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    trades: Mapped[list["SimulatedTrade"]] = relationship(  # noqa: F821, UP037
        back_populates="asset"
    )
