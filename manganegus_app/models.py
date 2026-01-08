"""
================================================================================
MangaNegus v3.1 - Database Models
================================================================================
SQLAlchemy ORM models for PostgreSQL database.

SCHEMA DESIGN:
  - manga: Rich metadata from sources + external APIs (AniList, MAL, etc.)
  - library: User's manga library (reading status, progress)
  - chapters: Chapter metadata cache
  - metadata_cache: External API response cache (TTL-based)
  - downloads: Track downloaded CBZ files

RELATIONSHIPS:
  - Library → Manga (many-to-one)
  - Manga → Chapters (one-to-many)
  - Manga → MetadataCache (one-to-many)
  - Downloads → Chapters (many-to-one)
================================================================================
"""

from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime,
    ForeignKey, JSON, Index, UniqueConstraint, Enum
)
from sqlalchemy.orm import relationship, DeclarativeBase
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
import uuid
import os

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


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# =============================================================================
# MANGA - Rich metadata from all sources
# =============================================================================

class Manga(Base):
    """
    Unified manga metadata from scraping sources + external APIs.

    This is the heart of the MetaForge system - combines data from:
    - MangaNegus sources (31 scrapers)
    - AniList (GraphQL API)
    - MyAnimeList via Jikan (REST API)
    - Kitsu (JSON:API)
    - Shikimori (REST API)
    - MangaUpdates (REST API)
    """
    __tablename__ = 'manga'

    # Primary key
    id = Column(UUIDType(), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Source identifiers (for linking to scraper results)
    source_id = Column(String(50), nullable=False, index=True)  # e.g., "mangadex"
    source_manga_id = Column(String(255), nullable=False, index=True)  # Source's internal ID
    source_url = Column(String(500))

    # External API IDs (for cross-referencing)
    anilist_id = Column(Integer, index=True)
    mal_id = Column(Integer, index=True)
    kitsu_id = Column(Integer, index=True)
    shikimori_id = Column(Integer, index=True)
    mangaupdates_id = Column(Integer, index=True)

    # Core metadata
    title = Column(String(500), nullable=False, index=True)
    title_english = Column(String(500))
    title_romaji = Column(String(500))
    title_native = Column(String(500))
    alt_titles = Column(JSONType)  # List of alternative titles

    # Rich description
    description = Column(Text)
    synopsis = Column(Text)  # From external APIs

    # Classification
    status = Column(Enum('releasing', 'finished', 'hiatus', 'cancelled',
                         'not_yet_released', name='manga_status'))
    manga_type = Column(String(50))  # manga, manhwa, manhua, novel, etc.

    # Content info
    genres = Column(JSONType)  # List of genre strings
    tags = Column(JSONType)  # Nuanced tags from AniList/MAL
    themes = Column(JSONType)  # From MAL
    demographics = Column(JSONType)  # Shounen, Seinen, etc.

    # People
    author = Column(String(255))
    artist = Column(String(255))
    authors = Column(JSONType)  # Full author list with roles

    # Popularity & ratings (aggregated from multiple sources)
    rating_average = Column(Float)  # 0-10 scale
    rating_anilist = Column(Float)
    rating_mal = Column(Float)
    rating_kitsu = Column(Float)

    popularity_score = Column(Integer)  # Combined metric
    favorites_count = Column(Integer)
    members_count = Column(Integer)  # MAL members

    rank = Column(Integer)
    popularity_rank = Column(Integer)

    # Structure
    chapters = Column(Integer)  # Total chapter count
    volumes = Column(Integer)

    # Media
    cover_image = Column(String(1000))  # Best quality cover
    cover_image_large = Column(String(1000))
    cover_image_medium = Column(String(1000))
    banner_image = Column(String(1000))

    # Publication
    year = Column(Integer, index=True)
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))

    # External links
    links = Column(JSONType)  # List of {site: str, url: str}

    # Metadata
    last_scraped_at = Column(DateTime(timezone=True), nullable=False,
                             default=lambda: datetime.now(timezone.utc))
    last_metadata_update = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Flags
    is_adult = Column(Boolean, default=False)
    is_licensed = Column(Boolean, default=False)

    # Relationships
    library_entries = relationship("LibraryEntry", back_populates="manga",
                                   cascade="all, delete-orphan")
    chapter_cache = relationship("ChapterCache", back_populates="manga",
                                 cascade="all, delete-orphan")
    metadata_cache = relationship("MetadataCache", back_populates="manga",
                                  cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        # Unique constraint on source + source_manga_id
        UniqueConstraint('source_id', 'source_manga_id',
                        name='uq_manga_source_id'),
        # Composite index for common queries
        Index('ix_manga_title_status', 'title', 'status'),
        Index('ix_manga_rating_popularity', 'rating_average', 'popularity_score'),
    )

    def __repr__(self):
        return f"<Manga(id={self.id}, title='{self.title}', source='{self.source_id}')>"


# =============================================================================
# LIBRARY - User's manga collection (replaces library.json)
# =============================================================================

class LibraryEntry(Base):
    """
    User's library - tracks reading status and progress.

    Replaces the old library.json file-based storage.
    """
    __tablename__ = 'library'

    id = Column(UUIDType(), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Link to manga
    manga_id = Column(UUIDType(), ForeignKey('manga.id', ondelete='CASCADE'),
                     nullable=False, index=True)

    # Reading status
    status = Column(Enum('reading', 'completed', 'plan_to_read', 'dropped',
                         'on_hold', name='reading_status'),
                   nullable=False, default='plan_to_read', index=True)

    # Progress tracking
    last_chapter_read = Column(String(50))  # Chapter number as string (e.g., "123.5")
    last_chapter_id = Column(String(255))  # Source's chapter ID
    last_page_read = Column(Integer, default=0)

    # User ratings
    user_rating = Column(Float)  # User's personal rating (0-10)

    # Timestamps
    added_at = Column(DateTime(timezone=True), nullable=False,
                     default=lambda: datetime.now(timezone.utc), index=True)
    last_read_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), nullable=False,
                       default=lambda: datetime.now(timezone.utc),
                       onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    manga = relationship("Manga", back_populates="library_entries")

    def __repr__(self):
        return f"<LibraryEntry(manga='{self.manga.title if self.manga else 'N/A'}', status='{self.status}')>"


# =============================================================================
# HISTORY - Recently viewed manga (lightweight and append-only)
# =============================================================================

class HistoryEntry(Base):
    """
    Tracks recently viewed manga so the History tab can be restored across sessions.
    """
    __tablename__ = 'history'

    id = Column(UUIDType(), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Link to manga
    manga_id = Column(UUIDType(), ForeignKey('manga.id', ondelete='CASCADE'),
                     nullable=False, index=True)

    # Tracking
    last_viewed_at = Column(DateTime(timezone=True), nullable=False,
                            default=lambda: datetime.now(timezone.utc), index=True)
    view_count = Column(Integer, default=1)

    # Optional extra payload for quick rendering (cover, author, etc.)
    payload = Column(JSONType)

    manga = relationship("Manga")

    __table_args__ = (
        UniqueConstraint('manga_id', name='uq_history_manga_id'),
    )

    def __repr__(self):
        return f"<HistoryEntry(manga='{self.manga.title if self.manga else 'N/A'}', last_viewed_at='{self.last_viewed_at}')>"


# =============================================================================
# CHAPTER CACHE - Store chapter metadata
# =============================================================================

class ChapterCache(Base):
    """
    Cache for chapter metadata from sources.

    Reduces API calls by storing chapter lists.
    """
    __tablename__ = 'chapters'

    id = Column(UUIDType(), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Link to manga
    manga_id = Column(UUIDType(), ForeignKey('manga.id', ondelete='CASCADE'),
                     nullable=False, index=True)

    # Source chapter ID
    source_chapter_id = Column(String(255), nullable=False, index=True)

    # Chapter info
    chapter_number = Column(String(50), index=True)  # e.g., "123.5"
    title = Column(String(500))
    volume = Column(String(20))

    # Language
    language = Column(String(10), default='en', index=True)

    # Groups/scanlators
    scanlator = Column(String(255))
    groups = Column(JSONType)  # List of scanlation groups

    # Pages
    page_count = Column(Integer)
    pages_data = Column(JSONType)  # List of page URLs (cached for offline)

    # Publication
    published_at = Column(DateTime(timezone=True))
    uploaded_at = Column(DateTime(timezone=True))

    # Metadata
    created_at = Column(DateTime(timezone=True), nullable=False,
                       default=lambda: datetime.now(timezone.utc))
    cached_at = Column(DateTime(timezone=True), nullable=False,
                      default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    manga = relationship("Manga", back_populates="chapter_cache")
    downloads = relationship("Download", back_populates="chapter",
                           cascade="all, delete-orphan")

    __table_args__ = (
        # Unique constraint on manga + source_chapter_id + language
        UniqueConstraint('manga_id', 'source_chapter_id', 'language',
                        name='uq_chapter_manga_source_lang'),
        Index('ix_chapter_number_lang', 'chapter_number', 'language'),
    )

    def __repr__(self):
        return f"<ChapterCache(manga_id={self.manga_id}, chapter='{self.chapter_number}')>"


# =============================================================================
# METADATA CACHE - External API response cache
# =============================================================================

class MetadataCache(Base):
    """
    TTL-based cache for external metadata API responses.

    Reduces API calls to AniList, MAL, Kitsu, etc.
    """
    __tablename__ = 'metadata_cache'

    id = Column(UUIDType(), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Link to manga (optional - some cache entries might be for ID mapping)
    manga_id = Column(UUIDType(), ForeignKey('manga.id', ondelete='CASCADE'),
                     index=True)

    # Cache key (provider + query/ID)
    provider = Column(String(50), nullable=False, index=True)  # "anilist", "mal", etc.
    cache_key = Column(String(500), nullable=False, index=True)  # Query or ID
    cache_type = Column(String(50), nullable=False)  # "search", "details", "id_map"

    # Cached response
    response_data = Column(JSONType, nullable=False)  # Full API response

    # TTL management
    created_at = Column(DateTime(timezone=True), nullable=False,
                       default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # Hit tracking
    hit_count = Column(Integer, default=0)
    last_hit_at = Column(DateTime(timezone=True))

    # Relationships
    manga = relationship("Manga", back_populates="metadata_cache")

    __table_args__ = (
        # Unique constraint on provider + cache_key + cache_type
        UniqueConstraint('provider', 'cache_key', 'cache_type',
                        name='uq_cache_provider_key_type'),
        Index('ix_cache_expires', 'expires_at'),
    )

    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return datetime.now(timezone.utc) > self.expires_at

    def __repr__(self):
        return f"<MetadataCache(provider='{self.provider}', key='{self.cache_key}')>"


# =============================================================================
# DOWNLOADS - Track downloaded CBZ files
# =============================================================================

class Download(Base):
    """
    Track downloaded manga chapters (CBZ files).

    Enables:
    - Offline reading
    - Download management
    - Storage optimization
    """
    __tablename__ = 'downloads'

    id = Column(UUIDType(), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Link to chapter
    chapter_id = Column(UUIDType(), ForeignKey('chapters.id', ondelete='CASCADE'),
                       nullable=False, index=True)

    # File info
    filename = Column(String(500), nullable=False, unique=True)  # CBZ filename
    file_path = Column(String(1000), nullable=False)  # Relative path in downloads/
    file_size = Column(Integer)  # Bytes

    # Download metadata
    downloaded_at = Column(DateTime(timezone=True), nullable=False,
                          default=lambda: datetime.now(timezone.utc), index=True)
    quality = Column(String(20))  # "hd" or "data_saver"

    # Status
    status = Column(Enum('downloading', 'completed', 'failed', 'deleted',
                         name='download_status'),
                   nullable=False, default='downloading', index=True)
    error_message = Column(Text)

    # Relationships
    chapter = relationship("ChapterCache", back_populates="downloads")

    __table_args__ = (
        Index('ix_download_status_downloaded', 'status', 'downloaded_at'),
    )

    def __repr__(self):
        return f"<Download(filename='{self.filename}', status='{self.status}')>"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def init_db(engine):
    """
    Initialize database - create all tables.

    Usage:
        from sqlalchemy import create_engine
        engine = create_engine('postgresql://user:pass@localhost/manganegus')
        init_db(engine)
    """
    Base.metadata.create_all(engine)


def drop_all_tables(engine):
    """
    Drop all tables (DANGEROUS - for development only).
    """
    Base.metadata.drop_all(engine)
