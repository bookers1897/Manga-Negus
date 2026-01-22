import os
import threading
import json
import time
import uuid
from datetime import datetime, timezone
import shutil
import zipfile
from typing import Dict, List, Optional, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from .log import log

# Import stealth headers for bot detection avoidance
try:
    from sources.stealth_headers import SessionFingerprint
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False
    SessionFingerprint = None

# Parallel download configuration
MAX_DOWNLOAD_WORKERS = 4

# =============================================================================
# FILE PATHS & DIRECTORIES (Centralized)
# =============================================================================
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "static", "downloads")
LIBRARY_FILE = os.path.join(BASE_DIR, "library.json")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "static", "images"), exist_ok=True)


# =============================================================================
# APPLICATION EXTENSIONS (Singleton Objects)
# =============================================================================

class Library:
    """Manages the user's manga library with PostgreSQL backend."""
    def __init__(self, filepath: str = None):
        self.filepath = filepath  # Kept for backwards compatibility
        self._lock = threading.RLock()
        self._use_db = self._check_database_available()
        if not self._use_db:
            log("⚠️ PostgreSQL not available, using file-based library")

    def _check_database_available(self) -> bool:
        """Check if PostgreSQL is available."""
        try:
            from .database import check_database_connection
            return check_database_connection()
        except Exception:
            return False

    def load(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Load library entries for a user. Returns dict compatible with old JSON format."""
        if self._use_db:
            if not user_id:
                return {}
            return self._load_from_db(str(user_id))
        return self._load_from_file(str(user_id) if user_id else None)

    def _load_from_db(self, user_id: str) -> Dict[str, Any]:
        """Load from PostgreSQL database with optimized eager loading."""
        try:
            from .database import get_db_session
            from .models import LibraryEntry, Manga
            from sqlalchemy.orm import joinedload

            with get_db_session() as session:
                # Eager load Manga data to prevent N+1 queries
                # This loads all manga data in a single JOIN query instead of 1 + N separate queries
                entries = session.query(LibraryEntry).options(
                    joinedload(LibraryEntry.manga)
                ).filter_by(user_id=str(user_id)).all()

                result = {}
                for entry in entries:
                    manga = entry.manga
                    key = f"{manga.source_id}:{manga.source_manga_id}"
                    result[key] = {
                        "title": manga.title,
                        "source": manga.source_id,
                        "manga_id": manga.source_manga_id,
                        "status": entry.status.value if hasattr(entry.status, 'value') else str(entry.status),
                        "cover": manga.cover_image,
                        "last_chapter": entry.last_chapter_read,
                        "last_chapter_id": entry.last_chapter_id,
                        "last_page": entry.last_page_read,
                        "total_chapters": manga.chapters,
                        "last_read_at": entry.last_read_at.isoformat() if entry.last_read_at else None,
                        "added_at": entry.added_at.strftime("%Y-%m-%d %H:%M:%S") if entry.added_at else None
                    }

                return result
        except Exception as e:
            log(f"❌ Database error, falling back to file: {e}")
            return self._load_from_file(user_id)

    def _load_from_file(self, user_id: Optional[str]) -> Dict[str, Any]:
        """Fallback to file-based storage."""
        if not user_id:
            return {}
        with self._lock:
            if not self.filepath or not os.path.exists(self.filepath):
                return {}
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        if not isinstance(data, dict):
            return {}
        if data and all(isinstance(k, str) and ':' in k for k in data.keys()):
            data = {user_id: data}
            if self.filepath:
                try:
                    with open(self.filepath, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
                except OSError:
                    pass
        user_db = data.get(user_id)
        return user_db if isinstance(user_db, dict) else {}

    def add(self, user_id: str, manga_id: str, title: str, source: str, status: str = 'reading', cover: Optional[str] = None) -> str:
        """Add manga to library."""
        if self._use_db:
            return self._add_to_db(str(user_id), manga_id, title, source, status, cover)
        return self._add_to_file(str(user_id) if user_id else None, manga_id, title, source, status, cover)

    def _add_to_db(self, user_id: str, manga_id: str, title: str, source: str, status: str, cover: Optional[str]) -> str:
        """Add to PostgreSQL database."""
        try:
            from .database import get_db_session
            from .models import LibraryEntry, Manga
            from datetime import datetime, timezone
            import uuid

            key = f"{source}:{manga_id}"

            with get_db_session() as session:
                # Check if manga exists (convert manga_id to string for VARCHAR column)
                manga = session.query(Manga).filter_by(
                    source_id=source,
                    source_manga_id=str(manga_id)
                ).first()

                if not manga:
                    # Create new manga record
                    now = datetime.now(timezone.utc)
                    manga = Manga(
                        id=str(uuid.uuid4()),
                        source_id=source,
                        source_manga_id=str(manga_id),  # Store as string
                        title=title,
                        cover_image=cover,
                        last_scraped_at=now,
                        created_at=now,
                        updated_at=now
                    )
                    session.add(manga)
                    session.flush()

                # Check if library entry exists
                library_entry = session.query(LibraryEntry).filter_by(
                    manga_id=manga.id,
                    user_id=str(user_id)
                ).first()

                # Validate and normalize status string (database uses string enums directly)
                valid_statuses = {'reading', 'completed', 'plan_to_read', 'dropped', 'on_hold'}
                reading_status = status if status in valid_statuses else 'reading'

                if library_entry:
                    # Update existing
                    library_entry.status = reading_status
                    library_entry.updated_at = datetime.now(timezone.utc)
                else:
                    # Create new entry
                    library_entry = LibraryEntry(
                        id=str(uuid.uuid4()),
                        manga_id=manga.id,
                        user_id=str(user_id),
                        status=reading_status,
                        added_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc)
                    )
                    session.add(library_entry)

                session.commit()
                log(f"📚 Added to library: {title}")
                return key

        except Exception as e:
            log(f"❌ Database error, falling back to file: {e}")
            return self._add_to_file(str(user_id) if user_id else None, manga_id, title, source, status, cover)

    def _add_to_file(self, user_id: Optional[str], manga_id: str, title: str, source: str, status: str, cover: Optional[str]) -> str:
        """Fallback to file-based storage."""
        if not user_id:
            return ""
        with self._lock:
            data = {}
            if self.filepath and os.path.exists(self.filepath):
                try:
                    with open(self.filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    data = {}
            if not isinstance(data, dict):
                data = {}
            if data and all(isinstance(k, str) and ':' in k for k in data.keys()):
                data = {user_id: data}
            user_db = data.get(user_id)
            if not isinstance(user_db, dict):
                user_db = {}
                data[user_id] = user_db

            key = f"{source}:{manga_id}"
            existing = user_db.get(key, {})
            user_db[key] = {
                "title": title, "source": source, "manga_id": manga_id,
                "status": status or existing.get('status', 'reading'),
                "cover": cover or existing.get('cover'),
                "last_chapter": existing.get('last_chapter'),
                "added_at": existing.get('added_at', time.strftime("%Y-%m-%d %H:%M:%S"))
            }

            data[user_id] = user_db
            if self.filepath:
                with open(self.filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
        log(f"📚 Added to library: {title}")
        return key

    def update_status(self, user_id: str, key: str, status: str) -> None:
        """Update reading status."""
        if self._use_db:
            self._update_status_db(str(user_id), key, status)
        else:
            self._update_status_file(str(user_id) if user_id else None, key, status)

    def _update_status_db(self, user_id: str, key: str, status: str) -> None:
        """Update status in database."""
        try:
            from .database import get_db_session
            from .models import LibraryEntry, Manga
            from datetime import datetime, timezone

            # Parse key: "source:manga_id"
            parts = key.split(':', 1)
            if len(parts) != 2:
                return
            source, manga_id = parts

            # Validate status string (database uses string enums directly)
            valid_statuses = {'reading', 'completed', 'plan_to_read', 'dropped', 'on_hold'}
            reading_status = status if status in valid_statuses else 'reading'

            with get_db_session() as session:
                manga = session.query(Manga).filter_by(
                    source_id=source,
                    source_manga_id=str(manga_id)  # Convert to string
                ).first()

                if manga:
                    library_entry = session.query(LibraryEntry).filter_by(
                        manga_id=manga.id,
                        user_id=str(user_id)
                    ).first()

                    if library_entry:
                        library_entry.status = reading_status
                        library_entry.updated_at = datetime.now(timezone.utc)
                        session.commit()
        except Exception as e:
            log(f"❌ Database error: {e}")
            self._update_status_file(str(user_id) if user_id else None, key, status)

    def _update_status_file(self, user_id: Optional[str], key: str, status: str) -> None:
        """Update status in file."""
        if not user_id:
            return
        with self._lock:
            data = {}
            if self.filepath and os.path.exists(self.filepath):
                try:
                    with open(self.filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    data = {}
            if not isinstance(data, dict):
                data = {}
            if data and all(isinstance(k, str) and ':' in k for k in data.keys()):
                data = {user_id: data}
            user_db = data.get(user_id)
            if not isinstance(user_db, dict):
                return
            if key in user_db:
                user_db[key]['status'] = status
                data[user_id] = user_db
                if self.filepath:
                    with open(self.filepath, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)

    def update_progress(self, user_id: str, key: str, chapter: str, page: Optional[int] = None, chapter_id: Optional[str] = None, total_chapters: Optional[int] = None, page_total: Optional[int] = None) -> None:
        """Update reading progress."""
        if self._use_db:
            self._update_progress_db(str(user_id), key, chapter, page=page, chapter_id=chapter_id, total_chapters=total_chapters, page_total=page_total)
        else:
            self._update_progress_file(str(user_id) if user_id else None, key, chapter, page=page, chapter_id=chapter_id, total_chapters=total_chapters, page_total=page_total)

    def _update_progress_db(self, user_id: str, key: str, chapter: str, page: Optional[int] = None, chapter_id: Optional[str] = None, total_chapters: Optional[int] = None, page_total: Optional[int] = None) -> None:
        """Update progress in database."""
        try:
            from .database import get_db_session
            from .models import LibraryEntry, Manga
            from datetime import datetime, timezone

            parts = key.split(':', 1)
            if len(parts) != 2:
                return
            source, manga_id = parts

            with get_db_session() as session:
                manga = session.query(Manga).filter_by(
                    source_id=source,
                    source_manga_id=str(manga_id)  # Convert to string
                ).first()

                if manga:
                    library_entry = session.query(LibraryEntry).filter_by(
                        manga_id=manga.id,
                        user_id=str(user_id)
                    ).first()

                    if library_entry:
                        library_entry.last_chapter_read = str(chapter)
                        if chapter_id:
                            library_entry.last_chapter_id = str(chapter_id)
                        if page is not None:
                            library_entry.last_page_read = int(page)
                        library_entry.last_read_at = datetime.now(timezone.utc)
                        library_entry.updated_at = datetime.now(timezone.utc)

                        if total_chapters is not None:
                            manga.chapters = int(total_chapters)

                        session.commit()
                        log(f"📖 Progress saved: Chapter {chapter} (page {page})")
        except Exception as e:
            log(f"❌ Database error: {e}")
            self._update_progress_file(str(user_id) if user_id else None, key, chapter, page=page, chapter_id=chapter_id, total_chapters=total_chapters, page_total=page_total)

    def _update_progress_file(self, user_id: Optional[str], key: str, chapter: str, page: Optional[int] = None, chapter_id: Optional[str] = None, total_chapters: Optional[int] = None, page_total: Optional[int] = None) -> None:
        """Update progress in file."""
        if not user_id:
            return
        with self._lock:
            data = {}
            if self.filepath and os.path.exists(self.filepath):
                try:
                    with open(self.filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    data = {}
            if not isinstance(data, dict):
                data = {}
            if data and all(isinstance(k, str) and ':' in k for k in data.keys()):
                data = {user_id: data}
            user_db = data.get(user_id)
            if not isinstance(user_db, dict):
                return
            if key in user_db:
                user_db[key]['last_chapter'] = str(chapter)
                if chapter_id:
                    user_db[key]['last_chapter_id'] = str(chapter_id)
                if page is not None:
                    user_db[key]['last_page'] = int(page)
                if page_total is not None:
                    user_db[key]['last_page_total'] = int(page_total)
                if total_chapters is not None:
                    user_db[key]['total_chapters'] = int(total_chapters)
                user_db[key]['last_read_at'] = datetime.now(timezone.utc).isoformat()
                data[user_id] = user_db
                if self.filepath:
                    with open(self.filepath, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
                log(f"📖 Progress saved: Chapter {chapter} (page {page})")

    def remove(self, user_id: str, key: str) -> None:
        """Remove manga from library."""
        if self._use_db:
            self._remove_from_db(str(user_id), key)
        else:
            self._remove_from_file(str(user_id) if user_id else None, key)

    def _remove_from_db(self, user_id: str, key: str) -> None:
        """Remove from database."""
        try:
            from .database import get_db_session
            from .models import LibraryEntry, Manga

            parts = key.split(':', 1)
            if len(parts) != 2:
                return
            source, manga_id = parts

            with get_db_session() as session:
                manga = session.query(Manga).filter_by(
                    source_id=source,
                    source_manga_id=str(manga_id)  # Convert to string
                ).first()

                if manga:
                    library_entry = session.query(LibraryEntry).filter_by(
                        manga_id=manga.id,
                        user_id=str(user_id)
                    ).first()

                    if library_entry:
                        title = manga.title
                        session.delete(library_entry)
                        session.commit()
                        log(f"🗑️ Removed: {title}")
        except Exception as e:
            log(f"❌ Database error: {e}")
            self._remove_from_file(str(user_id) if user_id else None, key)

    def _remove_from_file(self, user_id: Optional[str], key: str) -> None:
        """Remove from file."""
        if not user_id:
            return
        with self._lock:
            data = {}
            if self.filepath and os.path.exists(self.filepath):
                try:
                    with open(self.filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    data = {}
            if not isinstance(data, dict):
                data = {}
            if data and all(isinstance(k, str) and ':' in k for k in data.keys()):
                data = {user_id: data}
            user_db = data.get(user_id)
            if not isinstance(user_db, dict):
                return
            if key in user_db:
                title = user_db[key].get('title', 'Unknown')
                del user_db[key]
                data[user_id] = user_db
                if self.filepath:
                    with open(self.filepath, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
                log(f"🗑️ Removed: {title}")


# =============================================================================
# HISTORY - Track recently viewed manga
# =============================================================================
class History:
    """Tracks recently viewed manga, with DB + file fallback like Library."""
    def __init__(self, filepath: str = None):
        self.filepath = filepath or HISTORY_FILE
        self._lock = threading.RLock()
        self._use_db = self._check_database_available()
        if not self._use_db:
            log("ℹ️ History using file-based storage (database unavailable)")
        self._ensure_table()

    def _check_database_available(self) -> bool:
        try:
            from .database import check_database_connection
            return check_database_connection()
        except Exception:
            return False

    def _ensure_table(self):
        if not self._use_db:
            return
        try:
            from .database import get_engine
            from .models import HistoryEntry
            HistoryEntry.__table__.create(bind=get_engine(), checkfirst=True)
        except Exception as e:
            log(f"⚠️ Could not verify history table, will fallback to file if needed: {e}")
            self._use_db = False

    def load(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        if self._use_db:
            if not user_id:
                return []
            return self._load_from_db(str(user_id), limit)
        return self._load_from_file(str(user_id) if user_id else None, limit)

    def _load_from_db(self, user_id: str, limit: int) -> List[Dict[str, Any]]:
        try:
            from .database import get_db_session
            from .models import HistoryEntry

            with get_db_session() as session:
                entries = (
                    session.query(HistoryEntry)
                    .filter_by(user_id=str(user_id))
                    .order_by(HistoryEntry.last_viewed_at.desc())
                    .limit(limit)
                    .all()
                )

                result = []
                for entry in entries:
                    manga = entry.manga
                    result.append({
                        "id": manga.source_manga_id if manga else None,
                        "source": manga.source_id if manga else None,
                        "title": manga.title if manga else None,
                        "cover": manga.cover_image,
                        "cover_url": manga.cover_image,
                        "mal_id": manga.mal_id if manga else None,
                        "viewed_at": entry.last_viewed_at.isoformat() if entry.last_viewed_at else None,
                        "view_count": entry.view_count or 1,
                        "payload": entry.payload or {}
                    })
                return result
        except Exception as e:
            log(f"❌ History DB error, falling back to file: {e}")
            self._use_db = False
            return self._load_from_file(user_id, limit)

    def _load_from_file(self, user_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        if not user_id:
            return []
        with self._lock:
            if not self.filepath or not os.path.exists(self.filepath):
                return []
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        if not isinstance(data, dict):
            return []
        if data and all(isinstance(k, str) and ':' in k for k in data.keys()):
            data = {user_id: data}
            if self.filepath:
                try:
                    with open(self.filepath, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
                except OSError:
                    pass
        user_db = data.get(user_id)
        if not isinstance(user_db, dict):
            return []
        sorted_items = sorted(user_db.values(), key=lambda x: x.get('viewed_at') or '', reverse=True)
        return sorted_items[:limit]

    def add(self, user_id: str, manga_id: str, title: str, source: str, cover: Optional[str] = None, mal_id: Optional[int] = None, payload: Optional[Dict[str, Any]] = None) -> str:
        if self._use_db:
            return self._add_to_db(str(user_id), manga_id, title, source, cover, mal_id, payload or {})
        return self._add_to_file(str(user_id) if user_id else None, manga_id, title, source, cover, payload or {})

    def _add_to_db(self, user_id: str, manga_id: str, title: str, source: str, cover: Optional[str], mal_id: Optional[int], payload: Dict[str, Any]) -> str:
        try:
            from .database import get_db_session
            from .models import HistoryEntry, Manga
            import uuid

            key = f"{source}:{manga_id}"
            with get_db_session() as session:
                manga = session.query(Manga).filter_by(
                    source_id=source,
                    source_manga_id=str(manga_id)
                ).first()

                now = datetime.now(timezone.utc)

                if not manga:
                    manga = Manga(
                        id=str(uuid.uuid4()),
                        source_id=source,
                        source_manga_id=str(manga_id),
                        title=title,
                        cover_image=cover,
                        mal_id=mal_id,
                        last_scraped_at=now,
                        created_at=now,
                        updated_at=now
                    )
                    session.add(manga)
                    session.flush()

                entry = session.query(HistoryEntry).filter_by(
                    manga_id=manga.id,
                    user_id=str(user_id)
                ).first()
                if entry:
                    entry.last_viewed_at = now
                    entry.view_count = (entry.view_count or 0) + 1
                    entry.payload = payload or entry.payload
                else:
                    entry = HistoryEntry(
                        id=str(uuid.uuid4()),
                        manga_id=manga.id,
                        user_id=str(user_id),
                        last_viewed_at=now,
                        view_count=1,
                        payload=payload
                    )
                    session.add(entry)

                session.commit()
                log(f"🕑 Tracked history: {title}")
                return key
        except Exception as e:
            log(f"❌ History DB error, falling back to file: {e}")
            self._use_db = False
            return self._add_to_file(str(user_id) if user_id else None, manga_id, title, source, cover, payload)

    def _add_to_file(self, user_id: Optional[str], manga_id: str, title: str, source: str, cover: Optional[str], payload: Dict[str, Any]) -> str:
        if not user_id:
            return ""
        key = f"{source}:{manga_id}"
        with self._lock:
            data = {}
            if self.filepath and os.path.exists(self.filepath):
                try:
                    with open(self.filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    data = {}
            if not isinstance(data, dict):
                data = {}
            if data and all(isinstance(k, str) and ':' in k for k in data.keys()):
                data = {user_id: data}
            user_db = data.get(user_id)
            if not isinstance(user_db, dict):
                user_db = {}
                data[user_id] = user_db

            entry = user_db.get(key, {})
            entry.update({
                "id": manga_id,
                "title": title,
                "source": source,
                "cover": cover or entry.get('cover'),
                "viewed_at": datetime.now(timezone.utc).isoformat(),
                "view_count": entry.get('view_count', 0) + 1,
                "payload": payload or entry.get('payload', {})
            })
            user_db[key] = entry
            data[user_id] = user_db
            if self.filepath:
                with open(self.filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
        log(f"🕑 Tracked history (file): {title}")
        return key


class DownloadItem:
    """Represents a single download job in the queue.

    Status values:
    - paused_queue: Added but not started (user must manually start)
    - queued: Ready to download
    - downloading: Currently downloading
    - paused: User paused
    - completed: Finished
    - failed: Error occurred
    - cancelled: User cancelled
    """
    def __init__(self, job_id: str, chapters: List[Dict], title: str, source_id: str, manga_id: str = "", user_id: str = ""):
        self.job_id = job_id
        self.chapters = chapters
        self.title = title
        self.source_id = source_id
        self.manga_id = manga_id
        self.user_id = user_id or ""
        self.status = "queued"
        self.current_chapter_index = 0
        self.current_page = 0
        self.total_pages = 0
        self.error = None
        self.created_at = time.time()
        self.started_at = None
        self.completed_at = None

    def to_dict(self, include_user: bool = False) -> Dict[str, Any]:
        payload = {
            "job_id": self.job_id,
            "title": self.title,
            "source": self.source_id,
            "status": self.status,
            "chapters_total": len(self.chapters),
            "chapters_done": self.current_chapter_index,
            "current_page": self.current_page,
            "total_pages": self.total_pages,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at
        }
        if include_user:
            payload["user_id"] = self.user_id
        return payload


class Downloader:
    """Background chapter downloader with CBZ packaging and queue management."""
    def __init__(self, download_dir: str):
        self.download_dir = download_dir
        self._queue: List[DownloadItem] = []
        self._active_item: Optional[DownloadItem] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._pause_event = threading.Event()
        self._pause_event.set()  # Start unpaused
        self._stop_event = threading.Event()
        self._cancel_current = threading.Event()
        self._lock = threading.Lock()
        # Stealth fingerprint for consistent browser identity
        self._fingerprint = SessionFingerprint() if HAS_STEALTH else None
        self._start_worker()
    
    def _sanitize(self, name: str) -> str:
        return "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()

    def _sanitize_filename(self, name: str) -> str:
        clean = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_', '.')).strip()
        clean = clean.replace(os.sep, '_')
        if os.altsep:
            clean = clean.replace(os.altsep, '_')
        return clean or "untitled"

    def _user_dir(self, user_id: str) -> str:
        safe_user = self._sanitize_filename(user_id or "public")
        return os.path.join(self.download_dir, safe_user)

    def _start_worker(self):
        """Start the background worker thread that processes the queue."""
        def worker():
            while not self._stop_event.is_set():
                # Wait if paused
                self._pause_event.wait()

                # Get next item from queue
                item = None
                with self._lock:
                    for q_item in self._queue:
                        if q_item.status == "queued":
                            item = q_item
                            item.status = "downloading"
                            item.started_at = time.time()
                            self._active_item = item
                            break

                if item is None:
                    # No items to process, wait a bit
                    time.sleep(0.5)
                    continue

                # Process the download
                self._process_download(item)

                with self._lock:
                    self._active_item = None

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()

    def _process_download(self, item: DownloadItem):
        """Process a single download item."""
        from sources import get_source_manager

        manager = get_source_manager()
        source = manager.get_source(item.source_id)
        if not source and item.title:
            try:
                log(f"🔍 Resolving source for download: {item.title} (requested {item.source_id})")
                results = manager.search(item.title, source_id=None)
                if results:
                    best = results[0]
                    item.source_id = best.source
                    if best.id:
                        item.manga_id = best.id
                    source = manager.get_source(item.source_id)
            except Exception as exc:
                log(f"⚠️ Failed to resolve download source: {exc}")

        if not source:
            item.status = "failed"
            item.error = f"Source '{item.source_id}' not found"
            log(f"❌ {item.error}")
            return

        safe_title = self._sanitize(item.title) or "untitled"
        base_dir = self._user_dir(item.user_id)
        os.makedirs(base_dir, exist_ok=True)
        series_dir = os.path.join(base_dir, safe_title)
        os.makedirs(series_dir, exist_ok=True)
        log(f"🚀 Downloading {len(item.chapters)} chapters from {source.name}")

        # Fetch manga metadata for ComicInfo.xml
        manga_details = None
        if item.manga_id:
            try:
                manga_details = source.get_manga_details(item.manga_id)
            except Exception as e:
                log(f"⚠️ Failed to fetch manga details: {e}")

        download_session = getattr(source, "get_download_session", None)
        download_session = download_session() if callable(download_session) else source.session
        if not download_session:
            download_session = requests.Session()
            # Optimize connection pooling for parallel downloads
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=MAX_DOWNLOAD_WORKERS,
                pool_maxsize=MAX_DOWNLOAD_WORKERS * 2,
                max_retries=1
            )
            download_session.mount('http://', adapter)
            download_session.mount('https://', adapter)

        for idx, ch in enumerate(item.chapters[item.current_chapter_index:], start=item.current_chapter_index):
            # Check for pause
            self._pause_event.wait()

            # Check for cancel
            if self._cancel_current.is_set():
                item.status = "cancelled"
                self._cancel_current.clear()
                log("⏹️ Download cancelled")
                return

            item.current_chapter_index = idx
            ch_num = str(ch.get("chapter", "0"))
            ch_id = ch.get("id", "")

            try:
                pages = source.get_pages(ch_id)
                if not pages:
                    log(f"⚠️ No pages for Chapter {ch_num}")
                    continue

                item.total_pages = len(pages)
                item.current_page = 0

                safe_ch = self._sanitize_filename(ch_num)
                folder_name = f"{safe_title} - Ch{safe_ch}"
                log(f"⬇️ Ch {ch_num} ({len(pages)} pages)...")

                # Handle file sources (PDFs, EPUBs)
                if getattr(source, "is_file_source", False):
                    page = pages[0]
                    headers = dict(page.headers) if page.headers else {}
                    if page.referer:
                        headers['Referer'] = page.referer
                    source.wait_for_rate_limit()
                    resp = download_session.get(page.url, headers=headers, timeout=60, stream=True)
                    if resp.status_code != 200:
                        log(f"⚠️ Failed file download: HTTP {resp.status_code}")
                        continue
                    ct = resp.headers.get('Content-Type', '')
                    ext = os.path.splitext(page.url.split('?', 1)[0])[1] or ''
                    if not ext:
                        if 'pdf' in ct: ext = '.pdf'
                        elif 'epub' in ct: ext = '.epub'
                        elif 'cbz' in ct or 'zip' in ct: ext = '.cbz'
                        else: ext = '.bin'
                    filepath = os.path.join(series_dir, f"{folder_name}{ext}")
                    with open(filepath, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 256):
                            if chunk: f.write(chunk)
                    log(f"✅ Saved file: {folder_name}{ext}")
                    item.current_chapter_index = idx + 1
                    continue

                # Standard image download
                temp_folder = os.path.join(series_dir, folder_name)
                os.makedirs(temp_folder, exist_ok=True)
                self._write_comic_info(temp_folder, item.title, ch, source, manga_details)

                def download_single_page(page) -> Optional[Tuple[int, str, bytes]]:
                    """Download a single page with retries. Returns (index, ext, content) or None."""
                    for attempt in range(3):
                        try:
                            # Use stealth headers for bot detection avoidance
                            if self._fingerprint:
                                headers = self._fingerprint.get_image_headers(page.referer)
                            else:
                                headers = {}
                                if page.referer:
                                    headers['Referer'] = page.referer
                            # Merge page-specific headers
                            if page.headers:
                                headers.update(page.headers)
                            source.wait_for_rate_limit()
                            resp = download_session.get(page.url, headers=headers, timeout=20)
                            if resp.status_code == 200:
                                ext = '.jpg'
                                ct = resp.headers.get('Content-Type', '')
                                if 'png' in ct: ext = '.png'
                                elif 'webp' in ct: ext = '.webp'
                                return (page.index, ext, resp.content)
                        except Exception as e:
                            if attempt < 2:
                                time.sleep(0.5)
                    return None

                # Download pages in parallel with pause/cancel checks
                page_results = []
                cancelled = False
                with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS) as executor:
                    futures = {executor.submit(download_single_page, p): p for p in pages}
                    for future in as_completed(futures):
                        # Check for pause/cancel while collecting results
                        self._pause_event.wait()
                        if self._cancel_current.is_set():
                            # Cancel remaining futures
                            for f in futures:
                                f.cancel()
                            cancelled = True
                            break
                        result = future.result()
                        if result:
                            page_results.append(result)
                            # Update progress with highest completed page
                            item.current_page = max(item.current_page, result[0])

                if cancelled:
                    shutil.rmtree(temp_folder, ignore_errors=True)
                    item.status = "cancelled"
                    self._cancel_current.clear()
                    return

                # Write pages to disk in order
                for page_index, ext, content in sorted(page_results, key=lambda x: x[0]):
                    filepath = os.path.join(temp_folder, f"{page_index:03d}{ext}")
                    with open(filepath, 'wb') as f:
                        f.write(content)

                if len(page_results) < len(pages):
                    log(f"   ⚠️ {len(pages) - len(page_results)} pages failed")

                # Create CBZ
                cbz_path = os.path.join(series_dir, f"{folder_name}.cbz")
                with zipfile.ZipFile(cbz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for r, _, fs in os.walk(temp_folder):
                        for f in sorted(fs):
                            zf.write(os.path.join(r, f), arcname=f)
                shutil.rmtree(temp_folder)
                log(f"✅ Finished: Ch {ch_num}")
                item.current_chapter_index = idx + 1
                time.sleep(0.5)

            except Exception as e:
                log(f"❌ Error Ch {ch_num}: {e}")
                item.error = str(e)

        # Completed all chapters
        item.status = "completed"
        item.completed_at = time.time()
        log("✨ All downloads completed!")

    def add_to_queue(self, chapters: List[Dict], title: str, source_id: str, manga_id: str = "", start_immediately: bool = True, user_id: str = "") -> str:
        """Add a download job to the queue."""
        job_id = str(uuid.uuid4())
        item = DownloadItem(job_id, chapters, title, source_id, manga_id, user_id=user_id)

        if not start_immediately:
            item.status = "paused_queue"

        with self._lock:
            self._queue.append(item)

        log(f"📥 Added to queue: {title} ({len(chapters)} chapters) - {'auto-start' if start_immediately else 'paused'}")
        return job_id

    def start(self, chapters: List[Dict], title: str, source_id: str, manga_id: str = "", start_immediately: bool = True, user_id: str = "") -> str:
        """Backward-compatible wrapper for adding a download job."""
        return self.add_to_queue(chapters, title, source_id, manga_id, start_immediately, user_id=user_id)

    def cancel(self, job_id: str, user_id: Optional[str] = None) -> bool:
        """Cancel a download (queued or active)."""
        with self._lock:
            # If it's the active download, signal cancel
            if self._active_item and self._active_item.job_id == job_id:
                if user_id and self._active_item.user_id != user_id:
                    return False
                self._cancel_current.set()
                return True

            # Otherwise find in queue and mark cancelled
            for item in self._queue:
                if item.job_id == job_id and item.status in ("queued", "paused_queue"):
                    if user_id and item.user_id != user_id:
                        return False
                    item.status = "cancelled"
                    log(f"⏹️ Cancelled: {item.title}")
                    return True
        return False

    def pause(self, job_id: Optional[str] = None, user_id: Optional[str] = None) -> bool:
        """Pause downloads. If job_id is None, pause all."""
        if job_id is None:
            if user_id is not None:
                return False
            self._pause_event.clear()
            log("⏸️ Downloads paused")
            return True

        with self._lock:
            if self._active_item and self._active_item.job_id == job_id:
                if user_id and self._active_item.user_id != user_id:
                    return False
                self._active_item.status = "paused"
                self._pause_event.clear()
                log(f"⏸️ Paused: {self._active_item.title}")
                return True
        return False

    def resume(self, job_id: Optional[str] = None, user_id: Optional[str] = None) -> bool:
        """Resume downloads. If job_id is None, resume all."""
        if job_id is None:
            if user_id is not None:
                return False
            self._pause_event.set()
            log("▶️ Downloads resumed")
            return True

        with self._lock:
            if self._active_item and self._active_item.job_id == job_id:
                if user_id and self._active_item.user_id != user_id:
                    return False
                self._active_item.status = "downloading"
                self._pause_event.set()
                log(f"▶️ Resumed: {self._active_item.title}")
                return True

            # Check if paused in queue
            for item in self._queue:
                if item.job_id == job_id and item.status == "paused":
                    if user_id and item.user_id != user_id:
                        return False
                    item.status = "queued"
                    self._pause_event.set()
                    return True
        return False

    def start_paused_items(self, job_ids: Optional[List[str]] = None, user_id: Optional[str] = None) -> None:
        """Start paused queue items."""
        with self._lock:
            started_count = 0
            for item in self._queue:
                if item.status == "paused_queue" and (job_ids is None or item.job_id in job_ids):
                    if user_id and item.user_id != user_id:
                        continue
                    item.status = "queued"
                    started_count += 1

            if started_count:
                log(f"▶️ Started {started_count} paused downloads")

    def get_queue(self, user_id: Optional[str] = None, include_user: bool = False) -> Dict[str, Any]:
        """Get the current download queue status with paused count."""
        with self._lock:
            queue_data = []
            paused_count = 0
            active_count = 0
            completed_count = 0

            for item in self._queue:
                if user_id and item.user_id != user_id:
                    continue
                if item.status == "paused_queue":
                    paused_count += 1
                elif item.status in ("queued", "downloading", "paused"):
                    active_count += 1
                elif item.status in ("completed", "failed", "cancelled"):
                    completed_count += 1
                queue_data.append(item.to_dict(include_user=include_user))

            return {
                "queue": queue_data,
                "paused_count": paused_count,
                "active_count": active_count,
                "completed_count": completed_count
            }

    def clear_completed(self, user_id: Optional[str] = None) -> int:
        """Remove completed/cancelled/failed items from queue."""
        with self._lock:
            before = len(self._queue)
            if user_id:
                kept = []
                removed = 0
                for item in self._queue:
                    if item.user_id == user_id and item.status in ("completed", "failed", "cancelled"):
                        removed += 1
                        continue
                    kept.append(item)
                self._queue = kept
                return removed
            self._queue = [item for item in self._queue if item.status in ("queued", "downloading", "paused", "paused_queue")]
            return before - len(self._queue)

    def remove_from_queue(self, job_id: str, user_id: Optional[str] = None) -> bool:
        """Remove a specific item from queue (if not downloading)."""
        with self._lock:
            for i, item in enumerate(self._queue):
                if item.job_id == job_id and item.status != "downloading":
                    if user_id and item.user_id != user_id:
                        return False
                    del self._queue[i]
                    return True
        return False

    def is_paused(self) -> bool:
        """Check if downloads are paused."""
        return not self._pause_event.is_set()

    def _write_comic_info(self, folder: str, title: str, chapter: Dict, source: Any, manga_details: Any = None) -> None:
        """Generate ComicInfo.xml metadata file."""
        try:
            from xml.etree.ElementTree import Element, SubElement, tostring
            from xml.dom import minidom

            root = Element('ComicInfo')
            root.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
            root.set('xmlns:xsd', 'http://www.w3.org/2001/XMLSchema')

            SubElement(root, 'Title').text = chapter.get('title') or f"Chapter {chapter.get('chapter')}"
            SubElement(root, 'Series').text = title
            SubElement(root, 'Number').text = str(chapter.get('chapter', '0'))
            SubElement(root, 'Web').text = chapter.get('url', '')
            SubElement(root, 'Source').text = source.name

            if manga_details:
                if hasattr(manga_details, 'author') and manga_details.author:
                    SubElement(root, 'Writer').text = manga_details.author
                if hasattr(manga_details, 'description') and manga_details.description:
                    SubElement(root, 'Summary').text = manga_details.description
                if hasattr(manga_details, 'genres') and manga_details.genres:
                    SubElement(root, 'Genre').text = ", ".join(manga_details.genres)
                if hasattr(manga_details, 'status') and manga_details.status:
                    SubElement(root, 'Notes').text = f"Status: {manga_details.status}"

            SubElement(root, 'Manga').text = 'YesAndRightToLeft'

            xml_str = minidom.parseString(tostring(root)).toprettyxml(indent="   ")
            with open(os.path.join(folder, 'ComicInfo.xml'), 'w', encoding='utf-8') as f:
                f.write(xml_str)
        except Exception as e:
            log(f"⚠️ Failed to create ComicInfo.xml: {e}")

    def get_downloaded(self, title: str, user_id: Optional[str] = None) -> List[str]:
        safe_title = self._sanitize(title)
        base_dir = self._user_dir(user_id or "")
        series_dir = os.path.join(base_dir, safe_title)
        if not os.path.exists(series_dir): return []
        return [fn.replace('.cbz', '').rsplit(' - Ch', 1)[-1] for fn in os.listdir(series_dir) if fn.endswith('.cbz')]

# Instantiate the singletons
library = Library(LIBRARY_FILE)
history = History(HISTORY_FILE)
downloader = Downloader(DOWNLOAD_DIR)
