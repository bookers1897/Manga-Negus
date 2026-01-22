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
    is_admin = Column(Boolean, default=False)
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
            'is_admin': self.is_admin,
            'preferences': self.preferences
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

# Keep legacy names for now to avoid breaking imports during migration
Manga = SourceLink
Download = DownloadJob