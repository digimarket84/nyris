"""Table de journalisation des décisions de la stratégie.

Trace chaque évaluation du moteur (enter/exit/hold/skip) avec sa raison et le
contexte (indicateurs, niveaux, position). Aucune logique de stratégie ici :
les lignes sont produites par la couche `strategy.recorder` à partir d'une
`Decision` pure.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from nyris.models.base import Base

_PRICE = Numeric(20, 8)


class StrategyDecision(Base):
    __tablename__ = "strategy_decisions"
    __table_args__ = (
        UniqueConstraint(
            "asset_id", "timeframe", "candle_close_time", "params_key",
            name="uq_strategy_decision_candle",
        ),
        Index("ix_strategy_decisions_asset_id", "asset_id"),
        Index("ix_strategy_decisions_candle_close_time", "candle_close_time"),
        Index("ix_strategy_decisions_action", "action"),
        Index("ix_strategy_decisions_run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # temps LOGIQUE = clôture de la bougie source (déterministe, pas l'horloge)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    candle_close_time: Mapped[int] = mapped_column(BigInteger, nullable=False)

    close_price: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    ema_fast: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)
    ema_slow: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)
    ema_trend: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)
    atr: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)

    action: Mapped[str] = mapped_column(String(10), nullable=False)  # enter/exit/hold/skip
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    position_state: Mapped[str] = mapped_column(String(10), nullable=False)  # flat/open

    entry_price: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)
    take_profit_price: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)

    params_key: Mapped[str] = mapped_column(String(80), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    simulated_trade_id: Mapped[int | None] = mapped_column(
        ForeignKey("simulated_trades.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
