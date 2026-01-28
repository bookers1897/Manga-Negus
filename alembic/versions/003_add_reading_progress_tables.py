"""Add reading_progress and reading_history tables for NEG-16, NEG-32, NEG-33

Revision ID: 003_add_reading_progress
Revises: 002_add_user_preferences
Create Date: 2026-01-28

This migration adds:
1. reading_progress table - tracks per-chapter reading position
2. reading_history table - timeline of chapters read

These tables enable:
- Resume reading from exact page in any chapter
- "Continue Reading" feature showing in-progress manga
- Reading history timeline view
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '003_add_reading_progress'
down_revision: Union[str, Sequence[str], None] = '002_add_user_preferences'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create reading_progress and reading_history tables."""

    # 1. Create reading_progress table
    op.create_table('reading_progress',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('manga_id', sa.String(length=500), nullable=False),
        sa.Column('source_id', sa.String(length=50), nullable=False),
        sa.Column('chapter_id', sa.String(length=500), nullable=False),
        sa.Column('chapter_number', sa.String(length=50), nullable=True),
        sa.Column('current_page', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('total_pages', sa.Integer(), nullable=True),
        sa.Column('is_completed', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('last_read_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    # Indexes for reading_progress
    op.create_index('idx_reading_progress_user_manga', 'reading_progress',
                    ['user_id', 'manga_id'], unique=False)
    op.create_index('idx_reading_progress_last_read', 'reading_progress',
                    ['user_id', 'last_read_at'], unique=False)

    # Unique constraint: one progress entry per user/manga/chapter
    op.create_unique_constraint('uq_user_manga_chapter', 'reading_progress',
                               ['user_id', 'manga_id', 'chapter_id'])

    # 2. Create reading_history table
    op.create_table('reading_history',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('manga_id', sa.String(length=500), nullable=False),
        sa.Column('source_id', sa.String(length=50), nullable=False),
        sa.Column('manga_title', sa.String(length=500), nullable=True),
        sa.Column('manga_cover', sa.String(length=500), nullable=True),
        sa.Column('chapter_id', sa.String(length=500), nullable=False),
        sa.Column('chapter_num', sa.String(length=50), nullable=True),
        sa.Column('chapter_title', sa.String(length=500), nullable=True),
        sa.Column('pages_read', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('total_pages', sa.Integer(), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    # Indexes for reading_history
    op.create_index('idx_reading_history_user', 'reading_history',
                    ['user_id', 'read_at'], unique=False)
    op.create_index('idx_reading_history_manga', 'reading_history',
                    ['user_id', 'manga_id'], unique=False)


def downgrade() -> None:
    """Drop reading_progress and reading_history tables."""

    # Drop reading_history
    op.drop_index('idx_reading_history_manga', table_name='reading_history')
    op.drop_index('idx_reading_history_user', table_name='reading_history')
    op.drop_table('reading_history')

    # Drop reading_progress
    op.drop_constraint('uq_user_manga_chapter', 'reading_progress', type_='unique')
    op.drop_index('idx_reading_progress_last_read', table_name='reading_progress')
    op.drop_index('idx_reading_progress_user_manga', table_name='reading_progress')
    op.drop_table('reading_progress')
