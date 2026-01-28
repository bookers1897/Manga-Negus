"""Add search cache table

Revision ID: 004_add_search_cache
Revises: 003_add_reading_progress
Create Date: 2026-01-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '004_add_search_cache'
down_revision: Union[str, Sequence[str], None] = '003_add_reading_progress'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create search_cache table."""
    op.create_table(
        'search_cache',
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('key')
    )
    op.create_index('ix_search_cache_expires_at', 'search_cache', ['expires_at'], unique=False)


def downgrade() -> None:
    """Drop search_cache table."""
    op.drop_index('ix_search_cache_expires_at', table_name='search_cache')
    op.drop_table('search_cache')
