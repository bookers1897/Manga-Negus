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
    """Manages the user's manga library stored in JSON with in-memory caching."""
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._lock = threading.RLock()
        self._cache: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        with self._lock:
            if self._cache is not None:
                return self._cache.copy()
            if not os.path.exists(self.filepath):
                self._cache = {}
                return {}
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._cache = data
                return data.copy()
            except (json.JSONDecodeError, IOError):
                self._cache = {}
                return {}

    def _save(self, data: Dict[str, Any]) -> None:
        with self._lock:
            self._cache = data.copy()
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

    def add(self, manga_id: str, title: str, source: str, status: str = 'reading', cover: Optional[str] = None) -> str:
        db = self.load()
        key = f"{source}:{manga_id}"
        existing = db.get(key, {})
        db[key] = {
            "title": title, "source": source, "manga_id": manga_id,
            "status": status or existing.get('status', 'reading'),
            "cover": cover or existing.get('cover'),
            "last_chapter": existing.get('last_chapter'),
            "added_at": existing.get('added_at', time.strftime("%Y-%m-%d %H:%M:%S"))
        }
        self._save(db)
        log(f"📚 Added to library: {title}")
        return key
    
    def update_status(self, key: str, status: str) -> None:
        db = self.load()
        if key in db:
            db[key]['status'] = status
            self._save(db)

    def update_progress(self, key: str, chapter: str) -> None:
        db = self.load()
        if key in db:
            db[key]['last_chapter'] = str(chapter)
            self._save(db)
            log(f"📖 Progress saved: Chapter {chapter}")

    def remove(self, key: str) -> None:
        db = self.load()
        if key in db:
            title = db[key].get('title', 'Unknown')
            del db[key]
            self._save(db)
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
    
    def _is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return self._cancel.get(job_id, False)

    def start(self, chapters: List[Dict], title: str, source_id: str) -> str:
        from sources import get_source_manager
        job_id = f"{source_id}:{title}:{int(time.time())}"
        with self._lock:
            self._cancel[job_id] = False

        def worker():
            manager = get_source_manager()
            source = manager.get_source(source_id)
            if not source:
                log(f"❌ Source '{source_id}' not found")
                return
            safe_title = self._sanitize(title)
            series_dir = os.path.join(self.download_dir, safe_title)
            os.makedirs(series_dir, exist_ok=True)
            log(f"🚀 Downloading {len(chapters)} chapters from {source.name}")
            for ch in chapters:
                if self._is_cancelled(job_id):
                    log("⏹️ Download cancelled")
                    break
                ch_num = ch.get("chapter", "0")
                ch_id = ch.get("id", "")
                try:
                    pages = source.get_pages(ch_id)
                    if not pages:
                        log(f"⚠️ No pages for Chapter {ch_num}")
                        continue
                    folder_name = f"{safe_title} - Ch{ch_num}"
                    temp_folder = os.path.join(series_dir, folder_name)
                    os.makedirs(temp_folder, exist_ok=True)
                    log(f"⬇️ Ch {ch_num} ({len(pages)} pages)...")
                    download_session = source.session or requests.Session()
                    for page in pages:
                        if self._is_cancelled(job_id):
                            break
                        success = False
                        for attempt in range(3):
                            try:
                                headers = dict(page.headers) if page.headers else {}
                                if page.referer:
                                    headers['Referer'] = page.referer
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
    
    def get_downloaded(self, title: str) -> List[str]:
        safe_title = self._sanitize(title)
        series_dir = os.path.join(self.download_dir, safe_title)
        if not os.path.exists(series_dir): return []
        return [fn.replace('.cbz', '').rsplit(' - Ch', 1)[-1] for fn in os.listdir(series_dir) if fn.endswith('.cbz')]

# Instantiate the singletons
library = Library(LIBRARY_FILE)
downloader = Downloader(DOWNLOAD_DIR)
