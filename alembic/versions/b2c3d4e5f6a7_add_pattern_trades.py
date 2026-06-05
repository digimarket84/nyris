"""add pattern_trades table

Revision ID: b2c3d4e5f6a7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-05

Additive only : nouvelle table pattern_trades (bidirectionnel). Aucun impact baseline/short.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None

_MONEY = sa.Numeric(18, 2)
_PRICE = sa.Numeric(20, 8)
_QTY = sa.Numeric(30, 12)
_RATE = sa.Numeric(10, 6)
_PCT = sa.Numeric(9, 4)


def upgrade() -> None:
    op.create_table(
        "pattern_trades",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="open"),
        sa.Column("side", sa.String(length=5), nullable=False),
        sa.Column("pattern", sa.String(length=20), nullable=True),
        sa.Column("amount_invested", _MONEY, nullable=False),
        sa.Column("entry_price", _PRICE, nullable=False),
        sa.Column("quantity", _QTY, nullable=False),
        sa.Column("stop_price", _PRICE, nullable=True),
        sa.Column("take_profit_price", _PRICE, nullable=True),
        sa.Column("commission_rate", _RATE, nullable=False),
        sa.Column("spread_rate", _RATE, nullable=False),
        sa.Column("slippage_rate", _RATE, nullable=False),
        sa.Column("funding_rate_daily", _RATE, nullable=False),
        sa.Column("entry_cost", _MONEY, nullable=False),
        sa.Column("exit_cost", _MONEY, nullable=True),
        sa.Column("funding_cost", _MONEY, nullable=True),
        sa.Column("exit_price", _PRICE, nullable=True),
        sa.Column("pnl_gross", _MONEY, nullable=True),
        sa.Column("pnl_net", _MONEY, nullable=True),
        sa.Column("pnl_percent", _PCT, nullable=True),
        sa.Column("entry_reason", sa.String(length=40), nullable=True),
        sa.Column("exit_reason", sa.String(length=40), nullable=True),
        sa.Column("run_id", sa.String(length=40), nullable=True),
        sa.Column("params_key", sa.String(length=80), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )
    op.create_index("ix_pattern_trades_asset_id", "pattern_trades", ["asset_id"])
    op.create_index("ix_pattern_trades_status", "pattern_trades", ["status"])
    op.create_index("ix_pattern_trades_run_id", "pattern_trades", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_pattern_trades_run_id", table_name="pattern_trades")
    op.drop_index("ix_pattern_trades_status", table_name="pattern_trades")
    op.drop_index("ix_pattern_trades_asset_id", table_name="pattern_trades")
    op.drop_table("pattern_trades")
