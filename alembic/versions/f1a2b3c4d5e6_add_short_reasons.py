"""add entry_reason exit_reason on short_trades

Revision ID: f1a2b3c4d5e6
Revises: 8586720d9de6
Create Date: 2026-06-04

Additive only : deux colonnes nullable sur short_trades. Aucun impact baseline.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "8586720d9de6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("short_trades", sa.Column("entry_reason", sa.String(length=40), nullable=True))
    op.add_column("short_trades", sa.Column("exit_reason", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("short_trades", "exit_reason")
    op.drop_column("short_trades", "entry_reason")
