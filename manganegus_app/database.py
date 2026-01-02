"""
================================================================================
MangaNegus v3.1 - Database Configuration
================================================================================
SQLAlchemy database connection and session management.

USAGE:
    from manganegus_app.database import get_db_session, init_database

    # Initialize database (create tables)
    init_database()

    # Use in routes/services
    with get_db_session() as session:
        manga = session.query(Manga).filter_by(title="Naruto").first()

CONFIGURATION:
    Set environment variable: DATABASE_URL
    Format: postgresql://username:password@hostname:port/database

    Example:
        DATABASE_URL=postgresql://manganegus:password@localhost:5432/manganegus

    Fallback: SQLite for development if PostgreSQL not configured
================================================================================
"""

import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event, pool, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
import logging

from .models import Base

# Setup logging
logger = logging.getLogger(__name__)


# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

def get_database_url() -> str:
    """
    Get database URL from environment or use SQLite fallback.

    Priority:
      1. DATABASE_URL environment variable
      2. Fallback to SQLite (manganegus.db)

    Returns:
        Database connection string
    """
    db_url = os.environ.get('DATABASE_URL')

    if db_url:
        # Handle Heroku's postgres:// -> postgresql://
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        logger.info(f"Using PostgreSQL: {db_url.split('@')[1] if '@' in db_url else 'configured'}")
        return db_url

    # Fallback to SQLite for development
    sqlite_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'manganegus.db')
    db_url = f'sqlite:///{sqlite_path}'
    logger.warning(f"DATABASE_URL not set. Using SQLite fallback: {sqlite_path}")
    logger.warning("For production, set: export DATABASE_URL=postgresql://user:pass@localhost/manganegus")
    return db_url


def create_db_engine():
    """
    Create SQLAlchemy engine with optimized settings.

    PostgreSQL: Connection pooling for concurrent requests
    SQLite: WAL mode for better concurrency
    """
    db_url = get_database_url()
    is_sqlite = db_url.startswith('sqlite:///')

    if is_sqlite:
        # SQLite configuration
        engine = create_engine(
            db_url,
            echo=False,  # Set to True for SQL query logging
            connect_args={
                'check_same_thread': False,  # Allow multi-threaded access
                'timeout': 20  # Wait up to 20s for locks
            }
        )

        # Enable WAL mode for better concurrency
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    else:
        # PostgreSQL configuration
        engine = create_engine(
            db_url,
            echo=False,
            poolclass=QueuePool,
            pool_size=10,          # Number of persistent connections
            max_overflow=20,       # Additional connections under load
            pool_pre_ping=True,    # Verify connections before use
            pool_recycle=3600,     # Recycle connections every hour
            connect_args={
                'connect_timeout': 10,
                'options': '-c timezone=utc'  # Always use UTC
            }
        )

    logger.info(f"Database engine created: {'SQLite' if is_sqlite else 'PostgreSQL'}")
    return engine


# Global engine and session factory
_engine = None
_SessionLocal = None


def get_engine():
    """Get or create the global database engine."""
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


def get_session_factory():
    """Get or create the global session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False  # Keep objects usable after commit
        )
    return _SessionLocal


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Usage:
        with get_db_session() as session:
            manga = session.query(Manga).first()
            session.add(new_manga)
            session.commit()

    Auto-closes session and handles rollback on exceptions.
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()  # Auto-commit if no exception
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        session.close()


def get_db() -> Session:
    """
    Dependency injection for FastAPI/Flask routes (alternative pattern).

    Usage:
        @app.route('/api/manga')
        def get_manga():
            db = get_db()
            try:
                manga = db.query(Manga).all()
                return jsonify([m.title for m in manga])
            finally:
                db.close()
    """
    SessionLocal = get_session_factory()
    return SessionLocal()


# =============================================================================
# DATABASE INITIALIZATION
# =============================================================================

def init_database(drop_existing: bool = False):
    """
    Initialize database - create all tables.

    Args:
        drop_existing: If True, drop all tables first (DANGEROUS!)

    Usage:
        # First time setup
        init_database()

        # Reset database (dev only)
        init_database(drop_existing=True)
    """
    engine = get_engine()

    if drop_existing:
        logger.warning("⚠️ DROPPING ALL TABLES - THIS WILL DELETE ALL DATA!")
        Base.metadata.drop_all(engine)

    logger.info("Creating database tables...")
    Base.metadata.create_all(engine)
    logger.info("✅ Database tables created successfully!")


def check_database_connection() -> bool:
    """
    Test database connection.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ Database connection successful")
        return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False


# =============================================================================
# MIGRATION HELPERS
# =============================================================================

def migrate_from_json(library_json_path: str):
    """
    Migrate existing library.json to PostgreSQL.

    Args:
        library_json_path: Path to library.json file

    This function:
      1. Reads library.json
      2. Creates Manga entries for each manga
      3. Creates LibraryEntry for user's library
      4. Preserves reading status and progress
    """
    import json
    from .models import Manga, LibraryEntry
    from datetime import datetime, timezone

    logger.info(f"Starting migration from {library_json_path}...")

    if not os.path.exists(library_json_path):
        logger.warning(f"Library file not found: {library_json_path}")
        return

    with open(library_json_path, 'r', encoding='utf-8') as f:
        library_data = json.load(f)

    with get_db_session() as session:
        migrated_count = 0

        for manga_id, entry in library_data.items():
            # Create Manga entry
            manga = Manga(
                source_id=entry.get('source', 'unknown'),
                source_manga_id=manga_id,
                title=entry.get('title', 'Unknown'),
                cover_image=entry.get('cover'),
                status='releasing',  # Default status
                created_at=datetime.now(timezone.utc)
            )
            session.add(manga)
            session.flush()  # Get manga.id

            # Create LibraryEntry
            library_entry = LibraryEntry(
                manga_id=manga.id,
                status=entry.get('status', 'reading'),
                last_chapter_read=entry.get('last_chapter'),
                added_at=datetime.now(timezone.utc)
            )
            session.add(library_entry)

            migrated_count += 1

        session.commit()
        logger.info(f"✅ Migrated {migrated_count} manga from library.json to PostgreSQL")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_database_stats() -> dict:
    """
    Get database statistics.

    Returns:
        Dict with table counts and cache statistics
    """
    from .models import Manga, LibraryEntry, ChapterCache, MetadataCache, Download

    with get_db_session() as session:
        stats = {
            'manga_count': session.query(Manga).count(),
            'library_count': session.query(LibraryEntry).count(),
            'chapters_cached': session.query(ChapterCache).count(),
            'metadata_cache_entries': session.query(MetadataCache).count(),
            'downloads': session.query(Download).filter_by(status='completed').count(),
            'database_type': 'PostgreSQL' if not get_database_url().startswith('sqlite') else 'SQLite'
        }

    return stats


def cleanup_expired_cache():
    """
    Remove expired metadata cache entries.

    Run this periodically (e.g., daily cron job).
    """
    from .models import MetadataCache
    from datetime import datetime, timezone

    with get_db_session() as session:
        expired = session.query(MetadataCache).filter(
            MetadataCache.expires_at < datetime.now(timezone.utc)
        ).delete()

        session.commit()
        logger.info(f"🗑️ Cleaned up {expired} expired cache entries")
        return expired
