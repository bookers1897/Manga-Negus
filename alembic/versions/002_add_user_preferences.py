"""Add preferences JSON column to users table

Revision ID: 002_add_user_preferences
Revises: 001_add_user_auth
Create Date: 2026-01-28

This migration adds a JSON preferences column to store user settings
that can be synced across devices.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002_add_user_preferences'
down_revision: Union[str, Sequence[str], None] = '001_add_user_auth'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add preferences column to users table."""
    op.add_column('users',
        sa.Column('preferences', sa.JSON(), nullable=True, server_default='{}'))

    # Also add updated_at column for tracking profile changes
    op.add_column('users',
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.text('CURRENT_TIMESTAMP')))


def downgrade() -> None:
    """Remove preferences and updated_at columns from users table."""
    op.drop_column('users', 'preferences')
    op.drop_column('users', 'updated_at')
