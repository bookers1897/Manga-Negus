"""Add user authentication and user_id to library, history, downloads

Revision ID: 001_add_user_auth
Revises: 8e6ff8901f1e
Create Date: 2026-01-17

Migration Strategy:
1. Create users table
2. Add nullable user_id columns to library, history, downloads
3. Create 'anonymous' user for existing data migration
4. Update existing rows to point to anonymous user
5. Make user_id columns non-nullable with foreign key constraints
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision: str = '001_add_user_auth'
down_revision: Union[str, Sequence[str], None] = '8e6ff8901f1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed UUID for anonymous user (consistent across migrations)
ANONYMOUS_USER_ID = '00000000-0000-0000-0000-000000000001'


def upgrade() -> None:
    """Upgrade schema - add user authentication."""

    # 1. Create users table
    op.create_table('users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=True),
        sa.Column('oauth_provider', sa.String(length=50), nullable=True),
        sa.Column('oauth_provider_id', sa.String(length=255), nullable=True),
        sa.Column('display_name', sa.String(length=100), nullable=True),
        sa.Column('avatar_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('is_admin', sa.Boolean(), nullable=True, server_default='false'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email', name='uq_user_email'),
        sa.UniqueConstraint('oauth_provider', 'oauth_provider_id',
                           name='uq_user_oauth_provider_id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index('ix_user_oauth', 'users', ['oauth_provider', 'oauth_provider_id'],
                    unique=False)

    # 2. Create anonymous user for existing data
    # This user will own all pre-existing library/history/download entries
    op.execute(f"""
        INSERT INTO users (id, email, display_name, is_active, is_admin, created_at)
        VALUES (
            '{ANONYMOUS_USER_ID}',
            'anonymous@manganegus.local',
            'Anonymous',
            true,
            false,
            CURRENT_TIMESTAMP
        )
    """)

    # 3. Add nullable user_id columns to existing tables
    op.add_column('library',
        sa.Column('user_id', sa.UUID(), nullable=True))
    op.add_column('history',
        sa.Column('user_id', sa.UUID(), nullable=True))
    op.add_column('downloads',
        sa.Column('user_id', sa.UUID(), nullable=True))

    # 4. Update existing rows to point to anonymous user
    op.execute(f"UPDATE library SET user_id = '{ANONYMOUS_USER_ID}' WHERE user_id IS NULL")
    op.execute(f"UPDATE history SET user_id = '{ANONYMOUS_USER_ID}' WHERE user_id IS NULL")
    op.execute(f"UPDATE downloads SET user_id = '{ANONYMOUS_USER_ID}' WHERE user_id IS NULL")

    # 5. Make user_id non-nullable and add foreign key constraints
    op.alter_column('library', 'user_id', nullable=False)
    op.alter_column('history', 'user_id', nullable=False)
    op.alter_column('downloads', 'user_id', nullable=False)

    # 6. Create foreign key constraints
    op.create_foreign_key('fk_library_user_id', 'library', 'users',
                         ['user_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_history_user_id', 'history', 'users',
                         ['user_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_downloads_user_id', 'downloads', 'users',
                         ['user_id'], ['id'], ondelete='CASCADE')

    # 7. Create indexes for user_id lookups
    op.create_index('ix_library_user_id', 'library', ['user_id'], unique=False)
    op.create_index('ix_history_user_id', 'history', ['user_id'], unique=False)
    op.create_index('ix_downloads_user_id', 'downloads', ['user_id'], unique=False)

    # 8. Create composite indexes for common queries
    op.create_index('ix_library_user_status', 'library', ['user_id', 'status'], unique=False)
    op.create_index('ix_history_user_viewed', 'history', ['user_id', 'last_viewed_at'], unique=False)
    op.create_index('ix_download_user_status', 'downloads', ['user_id', 'status'], unique=False)

    # 9. Create unique constraints for user-specific entries
    # Library: unique per user per manga (one entry per user per manga)
    op.create_unique_constraint('uq_library_user_manga', 'library', ['user_id', 'manga_id'])

    # History: unique per user per manga (one history entry per user per manga)
    op.create_unique_constraint('uq_history_user_manga', 'history', ['user_id', 'manga_id'])


def downgrade() -> None:
    """Downgrade schema - remove user authentication."""

    # Drop new constraints
    op.drop_constraint('uq_library_user_manga', 'library', type_='unique')
    op.drop_constraint('uq_history_user_manga', 'history', type_='unique')

    # Drop composite indexes
    op.drop_index('ix_library_user_status', table_name='library')
    op.drop_index('ix_history_user_viewed', table_name='history')
    op.drop_index('ix_download_user_status', table_name='downloads')

    # Drop user_id indexes
    op.drop_index('ix_library_user_id', table_name='library')
    op.drop_index('ix_history_user_id', table_name='history')
    op.drop_index('ix_downloads_user_id', table_name='downloads')

    # Drop foreign key constraints
    op.drop_constraint('fk_library_user_id', 'library', type_='foreignkey')
    op.drop_constraint('fk_history_user_id', 'history', type_='foreignkey')
    op.drop_constraint('fk_downloads_user_id', 'downloads', type_='foreignkey')

    # Drop user_id columns
    op.drop_column('library', 'user_id')
    op.drop_column('history', 'user_id')
    op.drop_column('downloads', 'user_id')

    # Drop users table (will also delete anonymous user)
    op.drop_index('ix_user_oauth', table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
