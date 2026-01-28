"""
================================================================================
MangaNegus v4.0 - Database Models (Master Entity Architecture)
================================================================================
Refactored SQLAlchemy models for improved data integrity, authentication, and
multi-source aggregation.

NEW ARCHITECTURE:
  - Series (Master): Global entity representing "the book" (e.g., "One Piece").
    Holds unified metadata (title, author, genres) agnostic of source.
  - SourceLink (Child): A specific connection to a provider (e.g., MangaDex ID).
    Links a Series to a concrete scraping source.
  - User: Authentication via Flask-Login (UserMixin).
  - LibraryEntry: Links User -> Series (not SourceLink). Allows progress to
    persist even if the user switches sources.
  - DownloadJob: Persistent queue table for robust background downloads.

LEGACY COMPATIBILITY:
  - 'Manga' alias provided for 'SourceLink' to ease migration.
================================================================================
"""

from datetime import datetime, timezone
import uuid
import os
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, ForeignKey, Text, JSON, Float, Enum,
    UniqueConstraint, Index
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from flask_login import UserMixin as FlaskLoginUserMixin

# Use JSON for SQLite compatibility, JSONType for PostgreSQL performance
# SQLAlchemy will use JSONType on PostgreSQL, JSON on SQLite automatically
JSONType = JSON

# UUID type - use String for SQLite, UUID for PostgreSQL
def UUIDType():
    """Returns appropriate UUID column type for current database."""
    db_url = os.environ.get('DATABASE_URL', '')
    if db_url.startswith('postgres://') or db_url.startswith('postgresql://'):
        return PG_UUID(as_uuid=False)
    return String(36)  # SQLite fallback - stores UUID as string

Base = declarative_base()

# =============================================================================
# MIXINS
# =============================================================================

class TimestampMixin:
    """Adds created_at and updated_at timestamps to models."""
    @declared_attr
    def created_at(cls):
        return Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    @declared_attr
    def updated_at(cls):
        return Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

# =============================================================================
# USER & AUTHENTICATION
# =============================================================================

class User(Base, FlaskLoginUserMixin, TimestampMixin):
    """User model for authentication and preferences."""
    __tablename__ = 'users'

    id = Column(UUIDType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100))
    avatar_url = Column(String(500), nullable=True)  # Profile picture URL
    is_admin = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True)  # Track last login time
    preferences = Column(JSON, default={})
    
    # Relationships
    library_entries = relationship("LibraryEntry", back_populates="user", cascade="all, delete-orphan")
    history_entries = relationship("HistoryEntry", back_populates="user", cascade="all, delete-orphan")
    downloads = relationship("DownloadJob", back_populates="user")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'display_name': self.display_name,
            'avatar_url': self.avatar_url,
            'is_admin': self.is_admin,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'preferences': self.preferences,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# =============================================================================
# MANGA DATA MODEL (Master Entity Pattern)
# =============================================================================

class Series(Base, TimestampMixin):
    """
    Master entity for a manga series.
    Aggregates metadata from multiple sources (SourceLinks).
    """
    __tablename__ = 'series'

    id = Column(UUIDType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(500), nullable=False, index=True)
    slug = Column(String(500), index=True)  # Normalized title for matching
    
    # Unified Metadata
    description = Column(Text)
    author = Column(String(255))
    artist = Column(String(255))
    cover_image = Column(String(500))
    genres = Column(JSON, default=[])
    status = Column(String(50), default='unknown')  # ongoing, completed, etc.
    year = Column(Integer)
    mal_id = Column(Integer, unique=True, nullable=True)
    anilist_id = Column(Integer, unique=True, nullable=True)
    
    # Relationships
    source_links = relationship("SourceLink", back_populates="series", cascade="all, delete-orphan")
    library_entries = relationship("LibraryEntry", back_populates="series", cascade="all, delete-orphan")

class SourceLink(Base, TimestampMixin):
    """
    Links a Series to a specific provider (MangaDex, MangaFire, etc).
    Previously named 'Manga'.
    """
    __tablename__ = 'source_links'

    id = Column(UUIDType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    series_id = Column(UUIDType(), ForeignKey('series.id'), nullable=True)
    
    source_id = Column(String(50), nullable=False)  # e.g., 'mangadex'
    source_manga_id = Column(String(255), nullable=False)  # e.g., 'c0ee660b-...'
    
    # Source-specific metadata cache
    title = Column(String(500))
    cover_image = Column(String(500))
    url = Column(String(500))
    chapters_count = Column(Integer, default=0)
    last_scraped_at = Column(DateTime)
    
    # Relationships
    series = relationship("Series", back_populates="source_links")
    # Legacy relationship for backward compatibility
    library_entries = relationship("LibraryEntry", back_populates="manga")
    history_entries = relationship("HistoryEntry", back_populates="manga")

    __table_args__ = (
        # Ensure unique link per source
        # {'sqlite_autoincrement': True}, 
    )

# =============================================================================
# LIBRARY & HISTORY
# =============================================================================

class LibraryEntry(Base, TimestampMixin):
    """
    User's library entry.
    """
    __tablename__ = 'library_entries'

    id = Column(UUIDType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUIDType(), ForeignKey('users.id'), nullable=False)
    series_id = Column(UUIDType(), ForeignKey('series.id'), nullable=True)
    
    # Legacy/Direct support (if series_id is null)
    manga_id = Column(UUIDType(), ForeignKey('source_links.id'), nullable=True) 

    status = Column(Enum('reading', 'completed', 'plan_to_read', 'dropped', 'on_hold', name='read_status'), default='reading')
    user_rating = Column(Float, nullable=True)
    
    # Progress
    last_chapter_read = Column(String(50))
    last_page_read = Column(Integer)
    last_chapter_id = Column(String(255))
    last_read_at = Column(DateTime)

    # Relationships
    user = relationship("User", back_populates="library_entries")
    series = relationship("Series", back_populates="library_entries")
    manga = relationship("SourceLink", back_populates="library_entries")  # Legacy support

class HistoryEntry(Base):
    """
    Reading history log.
    """
    __tablename__ = 'history_entries'

    id = Column(UUIDType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUIDType(), ForeignKey('users.id'), nullable=False)
    
    # Link to specific source used
    manga_id = Column(UUIDType(), ForeignKey('source_links.id'), nullable=False)
    
    last_viewed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    view_count = Column(Integer, default=1)
    payload = Column(JSON)  # Extra context (chapter, page)

    user = relationship("User", back_populates="history_entries")
    manga = relationship("SourceLink", back_populates="history_entries")

# =============================================================================
# DOWNLOADS
# =============================================================================

class DownloadJob(Base, TimestampMixin):
    """Persistent download queue."""
    __tablename__ = 'download_jobs'

    id = Column(UUIDType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUIDType(), ForeignKey('users.id'), nullable=True)
    
    # Target
    title = Column(String(500), nullable=False)
    source_id = Column(String(50), nullable=False)
    manga_id = Column(String(255)) # Source-specific ID
    chapters = Column(JSON, nullable=False) # List of chapter dicts
    
    # State
    status = Column(String(20), default='queued') # queued, downloading, paused, completed, failed, cancelled
    total_chapters = Column(Integer, default=0)
    chapters_done = Column(Integer, default=0)
    current_chapter = Column(String(100))
    error_message = Column(Text)
    
    completed_at = Column(DateTime)

    user = relationship("User", back_populates="downloads")

    def to_dict(self):
        return {
            'job_id': self.id,
            'title': self.title,
            'source': self.source_id,
            'status': self.status,
            'chapters_total': self.total_chapters,
            'chapters_done': self.chapters_done,
            'error': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }

# =============================================================================
# CACHE MODELS
# =============================================================================

class MetadataCache(Base):
    """Cache for external metadata (MAL, AniList)."""
    __tablename__ = 'metadata_cache'
    
    key = Column(String(255), primary_key=True) # e.g. "title:naruto"
    data = Column(JSON, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ChapterCache(Base):
    """Cache for chapter lists from sources."""
    __tablename__ = 'chapter_cache'

    key = Column(String(255), primary_key=True) # e.g. "mangadex:c0ee..."
    chapters = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class SearchCache(Base):
    """Cache for advanced search results."""
    __tablename__ = 'search_cache'

    key = Column(String(255), primary_key=True)
    data = Column(JSON, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('ix_search_cache_expires_at', 'expires_at'),
    )


# =============================================================================
# READING PROGRESS & HISTORY (NEG-16, NEG-32, NEG-33)
# =============================================================================

class ReadingProgress(Base, TimestampMixin):
    """
    Tracks per-chapter reading progress.
    Allows users to resume reading from exact page in any chapter.
    """
    __tablename__ = 'reading_progress'

    id = Column(UUIDType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUIDType(), ForeignKey('users.id'), nullable=True)  # Optional for anon users
    manga_id = Column(String(500), nullable=False)  # source:manga_id format
    source_id = Column(String(50), nullable=False)
    chapter_id = Column(String(500), nullable=False)
    chapter_number = Column(String(50))  # e.g., "1", "1.5", "Special"
    current_page = Column(Integer, default=1)
    total_pages = Column(Integer)
    is_completed = Column(Boolean, default=False)
    last_read_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="reading_progress")

    __table_args__ = (
        Index('idx_reading_progress_user_manga', 'user_id', 'manga_id'),
        Index('idx_reading_progress_last_read', 'user_id', 'last_read_at'),
        UniqueConstraint('user_id', 'manga_id', 'chapter_id', name='uq_user_manga_chapter'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'manga_id': self.manga_id,
            'source_id': self.source_id,
            'chapter_id': self.chapter_id,
            'chapter_number': self.chapter_number,
            'current_page': self.current_page,
            'total_pages': self.total_pages,
            'is_completed': self.is_completed,
            'last_read_at': self.last_read_at.isoformat() if self.last_read_at else None
        }


class ReadingHistory(Base):
    """
    Reading history log for timeline view.
    Records each chapter read for history tracking.
    """
    __tablename__ = 'reading_history'

    id = Column(UUIDType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUIDType(), ForeignKey('users.id'), nullable=True)
    manga_id = Column(String(500), nullable=False)  # source:manga_id format
    source_id = Column(String(50), nullable=False)
    manga_title = Column(String(500))
    manga_cover = Column(String(500))
    chapter_id = Column(String(500), nullable=False)
    chapter_num = Column(String(50))
    chapter_title = Column(String(500))
    pages_read = Column(Integer, default=0)
    total_pages = Column(Integer)
    read_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="reading_history")

    __table_args__ = (
        Index('idx_reading_history_user', 'user_id', 'read_at'),
        Index('idx_reading_history_manga', 'user_id', 'manga_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'manga_id': self.manga_id,
            'source_id': self.source_id,
            'manga_title': self.manga_title,
            'manga_cover': self.manga_cover,
            'chapter_id': self.chapter_id,
            'chapter_num': self.chapter_num,
            'chapter_title': self.chapter_title,
            'pages_read': self.pages_read,
            'total_pages': self.total_pages,
            'read_at': self.read_at.isoformat() if self.read_at else None
        }

# Keep legacy names for now to avoid breaking imports during migration
Manga = SourceLink
Download = DownloadJob
