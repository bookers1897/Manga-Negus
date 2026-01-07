import os
import threading
import json
import time
import shutil
import zipfile
from typing import Dict, List, Optional, Any
import requests
from .log import log

# =============================================================================
# FILE PATHS & DIRECTORIES (Centralized)
# =============================================================================
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "static", "downloads")
LIBRARY_FILE = os.path.join(BASE_DIR, "library.json")

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

    def load(self) -> Dict[str, Any]:
        """Load library entries. Returns dict compatible with old JSON format."""
        if self._use_db:
            return self._load_from_db()
        else:
            return self._load_from_file()

    def _load_from_db(self) -> Dict[str, Any]:
        """Load from PostgreSQL database."""
        try:
            from .database import get_db_session
            from .models import LibraryEntry, Manga

            with get_db_session() as session:
                entries = session.query(LibraryEntry).join(Manga).all()

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
                        "added_at": entry.added_at.strftime("%Y-%m-%d %H:%M:%S") if entry.added_at else None
                    }

                return result
        except Exception as e:
            log(f"❌ Database error, falling back to file: {e}")
            return self._load_from_file()

    def _load_from_file(self) -> Dict[str, Any]:
        """Fallback to file-based storage."""
        with self._lock:
            if not self.filepath or not os.path.exists(self.filepath):
                return {}
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}

    def add(self, manga_id: str, title: str, source: str, status: str = 'reading', cover: Optional[str] = None) -> str:
        """Add manga to library."""
        if self._use_db:
            return self._add_to_db(manga_id, title, source, status, cover)
        else:
            return self._add_to_file(manga_id, title, source, status, cover)

    def _add_to_db(self, manga_id: str, title: str, source: str, status: str, cover: Optional[str]) -> str:
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
                    manga_id=manga.id
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
            return self._add_to_file(manga_id, title, source, status, cover)

    def _add_to_file(self, manga_id: str, title: str, source: str, status: str, cover: Optional[str]) -> str:
        """Fallback to file-based storage."""
        db = self._load_from_file()
        key = f"{source}:{manga_id}"
        existing = db.get(key, {})
        db[key] = {
            "title": title, "source": source, "manga_id": manga_id,
            "status": status or existing.get('status', 'reading'),
            "cover": cover or existing.get('cover'),
            "last_chapter": existing.get('last_chapter'),
            "added_at": existing.get('added_at', time.strftime("%Y-%m-%d %H:%M:%S"))
        }
        with self._lock:
            if self.filepath:
                with open(self.filepath, 'w', encoding='utf-8') as f:
                    json.dump(db, f, indent=4, ensure_ascii=False)
        log(f"📚 Added to library: {title}")
        return key

    def update_status(self, key: str, status: str) -> None:
        """Update reading status."""
        if self._use_db:
            self._update_status_db(key, status)
        else:
            self._update_status_file(key, status)

    def _update_status_db(self, key: str, status: str) -> None:
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
                        manga_id=manga.id
                    ).first()

                    if library_entry:
                        library_entry.status = reading_status
                        library_entry.updated_at = datetime.now(timezone.utc)
                        session.commit()
        except Exception as e:
            log(f"❌ Database error: {e}")
            self._update_status_file(key, status)

    def _update_status_file(self, key: str, status: str) -> None:
        """Update status in file."""
        db = self._load_from_file()
        if key in db:
            db[key]['status'] = status
            with self._lock:
                if self.filepath:
                    with open(self.filepath, 'w', encoding='utf-8') as f:
                        json.dump(db, f, indent=4, ensure_ascii=False)

    def update_progress(self, key: str, chapter: str) -> None:
        """Update reading progress."""
        if self._use_db:
            self._update_progress_db(key, chapter)
        else:
            self._update_progress_file(key, chapter)

    def _update_progress_db(self, key: str, chapter: str) -> None:
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
                        manga_id=manga.id
                    ).first()

                    if library_entry:
                        library_entry.last_chapter_read = str(chapter)
                        library_entry.last_read_at = datetime.now(timezone.utc)
                        library_entry.updated_at = datetime.now(timezone.utc)
                        session.commit()
                        log(f"📖 Progress saved: Chapter {chapter}")
        except Exception as e:
            log(f"❌ Database error: {e}")
            self._update_progress_file(key, chapter)

    def _update_progress_file(self, key: str, chapter: str) -> None:
        """Update progress in file."""
        db = self._load_from_file()
        if key in db:
            db[key]['last_chapter'] = str(chapter)
            with self._lock:
                if self.filepath:
                    with open(self.filepath, 'w', encoding='utf-8') as f:
                        json.dump(db, f, indent=4, ensure_ascii=False)
            log(f"📖 Progress saved: Chapter {chapter}")

    def remove(self, key: str) -> None:
        """Remove manga from library."""
        if self._use_db:
            self._remove_from_db(key)
        else:
            self._remove_from_file(key)

    def _remove_from_db(self, key: str) -> None:
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
                        manga_id=manga.id
                    ).first()

                    if library_entry:
                        title = manga.title
                        session.delete(library_entry)
                        session.commit()
                        log(f"🗑️ Removed: {title}")
        except Exception as e:
            log(f"❌ Database error: {e}")
            self._remove_from_file(key)

    def _remove_from_file(self, key: str) -> None:
        """Remove from file."""
        db = self._load_from_file()
        if key in db:
            title = db[key].get('title', 'Unknown')
            del db[key]
            with self._lock:
                if self.filepath:
                    with open(self.filepath, 'w', encoding='utf-8') as f:
                        json.dump(db, f, indent=4, ensure_ascii=False)
            log(f"🗑️ Removed: {title}")


class Downloader:
    """Background chapter downloader with CBZ packaging."""
    def __init__(self, download_dir: str):
        self.download_dir = download_dir
        self._active: Dict[str, threading.Thread] = {}
        self._cancel: Dict[str, bool] = {}
        self._lock = threading.Lock()
    
    def _sanitize(self, name: str) -> str:
        return "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()

    def _sanitize_filename(self, name: str) -> str:
        clean = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_', '.')).strip()
        clean = clean.replace(os.sep, '_')
        if os.altsep:
            clean = clean.replace(os.altsep, '_')
        return clean or "untitled"
    
    def _is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return self._cancel.get(job_id, False)

    def start(self, chapters: List[Dict], title: str, source_id: str, manga_id: str = "") -> str:
        from sources import get_source_manager
        job_id = f"{source_id}:{title}:{int(time.time())}"
        with self._lock:
            self._cancel[job_id] = False

        def worker():
            manager = get_source_manager()
            source = manager.get_source(source_id)
            if not source:
                log(f"❌ Source '{source_id}' not found")
                with self._lock:
                    if job_id in self._active:
                        del self._active[job_id]
                    if job_id in self._cancel:
                        del self._cancel[job_id]
                return
            safe_title = self._sanitize(title)
            if not safe_title:
                safe_title = "untitled"
            series_dir = os.path.join(self.download_dir, safe_title)
            os.makedirs(series_dir, exist_ok=True)
            log(f"🚀 Downloading {len(chapters)} chapters from {source.name}")
            
            # Fetch full manga metadata for ComicInfo.xml
            manga_details = None
            if manga_id:
                try:
                    manga_details = source.get_manga_details(manga_id)
                except Exception as e:
                    log(f"⚠️ Failed to fetch manga details for metadata: {e}")

            for ch in chapters:
                if self._is_cancelled(job_id):
                    log("⏹️ Download cancelled")
                    break
                ch_num = str(ch.get("chapter", "0"))
                ch_id = ch.get("id", "")
                try:
                    pages = source.get_pages(ch_id)
                    if not pages:
                        log(f"⚠️ No pages for Chapter {ch_num}")
                        continue
                    safe_ch = self._sanitize_filename(ch_num)
                    folder_name = f"{safe_title} - Ch{safe_ch}"
                    log(f"⬇️ Ch {ch_num} ({len(pages)} pages)...")
                    download_session = getattr(source, "get_download_session", None)
                    download_session = download_session() if callable(download_session) else source.session
                    if not download_session:
                        download_session = requests.Session()

                    if getattr(source, "is_file_source", False):
                        page = pages[0]
                        headers = dict(page.headers) if page.headers else {}
                        if page.referer:
                            headers['Referer'] = page.referer
                        source.wait_for_rate_limit()
                        resp = download_session.get(page.url, headers=headers, timeout=60, stream=True)
                        if resp.status_code != 200:
                            log(f"⚠️ Failed file download for Chapter {ch_num}: HTTP {resp.status_code}")
                            continue
                        ct = resp.headers.get('Content-Type', '')
                        ext = os.path.splitext(page.url.split('?', 1)[0])[1] or ''
                        if not ext:
                            if 'pdf' in ct: ext = '.pdf'
                            elif 'epub' in ct: ext = '.epub'
                            elif 'cbz' in ct or 'zip' in ct: ext = '.cbz'
                            else: ext = '.bin'
                        filename = f"{folder_name}{ext}"
                        filepath = os.path.join(series_dir, filename)
                        with open(filepath, 'wb') as f:
                            for chunk in resp.iter_content(chunk_size=1024 * 256):
                                if chunk: f.write(chunk)
                        log(f"✅ Saved file: {filename}")
                        continue

                    temp_folder = os.path.join(series_dir, folder_name)
                    os.makedirs(temp_folder, exist_ok=True)
                    
                    # Create ComicInfo.xml
                    self._write_comic_info(temp_folder, title, ch, source, manga_details)

                    for page in pages:
                        if self._is_cancelled(job_id):
                            break
                        success = False
                        for attempt in range(3):
                            try:
                                headers = dict(page.headers) if page.headers else {}
                                if page.referer:
                                    headers['Referer'] = page.referer
                                source.wait_for_rate_limit()
                                resp = download_session.get(page.url, headers=headers, timeout=30)
                                if resp.status_code == 200:
                                    ext = '.jpg'
                                    ct = resp.headers.get('Content-Type', '')
                                    if 'png' in ct: ext = '.png'
                                    elif 'webp' in ct: ext = '.webp'
                                    filepath = os.path.join(temp_folder, f"{page.index:03d}{ext}")
                                    with open(filepath, 'wb') as f: f.write(resp.content)
                                    success = True
                                    break
                            except Exception as e:
                                log(f"   ⚠️ Retry {attempt + 1}/3 for page {page.index}: {e}")
                                time.sleep(1)
                        if not success:
                            log(f"   ⚠️ Failed page {page.index}")
                        time.sleep(0.1)
                    with zipfile.ZipFile(os.path.join(series_dir, f"{folder_name}.cbz"), 'w', zipfile.ZIP_DEFLATED) as zf:
                        for r, _, fs in os.walk(temp_folder):
                            for f in sorted(fs):
                                zf.write(os.path.join(r, f), arcname=f)
                    shutil.rmtree(temp_folder)
                    log(f"✅ Finished: Ch {ch_num}")
                    time.sleep(0.5)
                except Exception as e:
                    log(f"❌ Error Ch {ch_num}: {e}")
            log("✨ All downloads completed!")
            with self._lock:
                if job_id in self._active: del self._active[job_id]
                if job_id in self._cancel: del self._cancel[job_id]

        thread = threading.Thread(target=worker, daemon=True)
        with self._lock:
            self._active[job_id] = thread
        thread.start()
        return job_id

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._cancel:
                self._cancel[job_id] = True
                return True
            return False
    
    def _write_comic_info(self, folder: str, title: str, chapter: Dict, source: Any, manga_details: Any = None) -> None:
        """Generate ComicInfo.xml metadata file."""
        try:
            from xml.etree.ElementTree import Element, SubElement, tostring
            from xml.dom import minidom

            root = Element('ComicInfo')
            root.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
            root.set('xmlns:xsd', 'http://www.w3.org/2001/XMLSchema')

            # Basic Info
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

            # Manga specific
            SubElement(root, 'Manga').text = 'YesAndRightToLeft'

            xml_str = minidom.parseString(tostring(root)).toprettyxml(indent="   ")
            with open(os.path.join(folder, 'ComicInfo.xml'), 'w', encoding='utf-8') as f:
                f.write(xml_str)
        except Exception as e:
            log(f"⚠️ Failed to create ComicInfo.xml: {e}")

    def get_downloaded(self, title: str) -> List[str]:
        safe_title = self._sanitize(title)
        series_dir = os.path.join(self.download_dir, safe_title)
        if not os.path.exists(series_dir): return []
        return [fn.replace('.cbz', '').rsplit(' - Ch', 1)[-1] for fn in os.listdir(series_dir) if fn.endswith('.cbz')]

# Instantiate the singletons
library = Library(LIBRARY_FILE)
downloader = Downloader(DOWNLOAD_DIR)
