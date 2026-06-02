"""extend assets (display_name, exchange_symbol, status, is_tradeable, notes)

Revision ID: 386e4fcbffb5
Revises: 0a0856b12af6
Create Date: 2026-06-02 07:30:11.158789

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '386e4fcbffb5'
down_revision: Union[str, None] = '0a0856b12af6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Créer explicitement le type enum PostgreSQL (op.add_column ne le fait pas).
    asset_status = postgresql.ENUM('active', 'watch_only', 'delisted', name='asset_status')
    asset_status.create(op.get_bind(), checkfirst=True)

    op.add_column('assets', sa.Column('display_name', sa.String(length=100), nullable=False))
    op.add_column('assets', sa.Column('exchange_symbol', sa.String(length=40), nullable=False))
    op.add_column(
        'assets',
        sa.Column(
            'status',
            sa.Enum('active', 'watch_only', 'delisted', name='asset_status', create_type=False),
            nullable=False,
        ),
    )
    op.add_column('assets', sa.Column('is_tradeable', sa.Boolean(), nullable=False))
    op.add_column('assets', sa.Column('notes', sa.Text(), nullable=True))
    op.create_index(op.f('ix_assets_status'), 'assets', ['status'], unique=False)
    op.drop_column('assets', 'is_active')
    op.drop_column('assets', 'name')


def downgrade() -> None:
    op.add_column('assets', sa.Column('name', sa.VARCHAR(length=100), autoincrement=False, nullable=False))
    op.add_column('assets', sa.Column('is_active', sa.BOOLEAN(), autoincrement=False, nullable=False))
    op.drop_index(op.f('ix_assets_status'), table_name='assets')
    op.drop_column('assets', 'notes')
    op.drop_column('assets', 'is_tradeable')
    op.drop_column('assets', 'status')
    op.drop_column('assets', 'exchange_symbol')
    op.drop_column('assets', 'display_name')
    postgresql.ENUM(name='asset_status').drop(op.get_bind(), checkfirst=True)
