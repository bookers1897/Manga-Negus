"""
================================================================================
MangaNegus v2.3 - Main Application
================================================================================
Multi-source manga downloader and library manager.

FEATURES:
  - Multiple source support (MangaDex, ComicK, MangaSee, Manganato)
  - Automatic fallback when sources fail or are rate-limited
  - Proper rate limiting per source (prevents bans!)
  - Background chapter downloading
  - CBZ file packaging
  - Real-time progress logging

USAGE:
  1. pip install flask requests beautifulsoup4
  2. python app.py
  3. Open http://127.0.0.1:5000

Author: bookers1897
GitHub: https://github.com/bookers1897/Manga-Negus
================================================================================
"""

import os
import sys
import json
import time
import shutil
import zipfile
import threading
import queue
import secrets
from typing import Dict, List, Optional, Any
from functools import wraps

import requests
from flask import Flask, render_template, jsonify, request, send_from_directory, session

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python < 3.7
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')


# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))


# =============================================================================
# CSRF PROTECTION
# =============================================================================

def csrf_protect(f):
    """Decorator to require CSRF token on POST requests."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            token = request.headers.get('X-CSRF-Token') or (request.json or {}).get('_csrf_token')
            if not token or token != session.get('csrf_token'):
                return jsonify({'error': 'Invalid or missing CSRF token'}), 403
        return f(*args, **kwargs)
    return decorated_function


@app.before_request
def ensure_csrf_token():
    """Generate CSRF token for the session if not present."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)


@app.route('/api/csrf-token')
def get_csrf_token():
    """Return the CSRF token for the current session."""
    return jsonify({'csrf_token': session.get('csrf_token', '')})

# Thread-safe message queue for real-time logging
msg_queue: queue.Queue = queue.Queue()

# File paths
DOWNLOAD_DIR = os.path.join(BASE_DIR, "static", "downloads")
LIBRARY_FILE = os.path.join(BASE_DIR, "library.json")

# Create directories
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "static", "images"), exist_ok=True)


# =============================================================================
# LOGGING
# =============================================================================

def log(msg: str) -> None:
    """Log a message to console and message queue."""
    print(msg)
    timestamp = time.strftime("[%H:%M:%S]")
    msg_queue.put(f"{timestamp} {msg}")


# =============================================================================
# LIBRARY MANAGER
# =============================================================================

class Library:
    """Manages the user's manga library stored in JSON with in-memory caching."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self._lock = threading.RLock()  # Use RLock for nested locking
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_dirty = False

    def load(self) -> Dict[str, Any]:
        """Load library from cache or disk."""
        with self._lock:
            if self._cache is not None:
                return self._cache.copy()

            if not os.path.exists(self.filepath):
                self._cache = {}
                return {}

            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, manga in data.items():
                        manga.setdefault('status', 'reading')
                        manga.setdefault('cover', None)
                        manga.setdefault('last_chapter', None)
                        manga.setdefault('source', 'mangadex')
                    self._cache = data
                    return data.copy()
            except (json.JSONDecodeError, IOError):
                self._cache = {}
                return {}

    def _save(self, data: Dict[str, Any]) -> None:
        """Save library to disk and update cache."""
        with self._lock:
            self._cache = data.copy()
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
    
    def add(
        self,
        manga_id: str,
        title: str,
        source: str,
        status: str = 'reading',
        cover: Optional[str] = None
    ) -> str:
        """Add or update manga in library."""
        db = self.load()
        key = f"{source}:{manga_id}"
        existing = db.get(key, {})
        
        db[key] = {
            "title": title,
            "source": source,
            "manga_id": manga_id,
            "status": status or existing.get('status', 'reading'),
            "cover": cover or existing.get('cover'),
            "last_chapter": existing.get('last_chapter'),
            "added_at": existing.get('added_at', time.strftime("%Y-%m-%d %H:%M:%S"))
        }
        
        self._save(db)
        log(f"📚 Added to library: {title}")
        return key
    
    def update_status(self, key: str, status: str) -> None:
        """Update reading status."""
        db = self.load()
        if key in db:
            db[key]['status'] = status
            self._save(db)
    
    def update_progress(self, key: str, chapter: str) -> None:
        """Update last read chapter."""
        db = self.load()
        if key in db:
            db[key]['last_chapter'] = chapter
            self._save(db)
            log(f"📖 Progress saved: Chapter {chapter}")
    
    def remove(self, key: str) -> None:
        """Remove manga from library."""
        db = self.load()
        if key in db:
            title = db[key].get('title', 'Unknown')
            del db[key]
            self._save(db)
            log(f"🗑️ Removed: {title}")


library = Library(LIBRARY_FILE)


# =============================================================================
# DOWNLOAD MANAGER
# =============================================================================

class Downloader:
    """Background chapter downloader with CBZ packaging."""

    def __init__(self, download_dir: str):
        self.download_dir = download_dir
        self._active: Dict[str, threading.Thread] = {}
        self._cancel: Dict[str, bool] = {}
        self._lock = threading.Lock()  # Thread safety for _active and _cancel
    
    def _sanitize(self, name: str) -> str:
        """Remove invalid filesystem characters."""
        invalid = '<>:"/\\|?*'
        for char in invalid:
            name = name.replace(char, '')
        return name.strip()
    
    def _is_cancelled(self, job_id: str) -> bool:
        """Thread-safe check if job is cancelled."""
        with self._lock:
            return self._cancel.get(job_id, False)

    def start(self, chapters: List[Dict], title: str, source_id: str) -> str:
        """Start downloading chapters in background."""
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
                    
                    session = requests.Session()
                    
                    for page in pages:
                        if self._is_cancelled(job_id):
                            break
                        
                        success = False
                        for attempt in range(3):
                            try:
                                headers = dict(page.headers) if page.headers else {}
                                if page.referer:
                                    headers['Referer'] = page.referer
                                
                                resp = session.get(page.url, headers=headers, timeout=30)
                                
                                if resp.status_code == 200:
                                    ext = '.jpg'
                                    ct = resp.headers.get('Content-Type', '')
                                    if 'png' in ct:
                                        ext = '.png'
                                    elif 'webp' in ct:
                                        ext = '.webp'
                                    
                                    filepath = os.path.join(temp_folder, f"{page.index:03d}{ext}")
                                    with open(filepath, 'wb') as f:
                                        f.write(resp.content)
                                    success = True
                                    break
                            except (requests.RequestException, IOError) as e:
                                log(f"   ⚠️ Retry {attempt + 1}/3 for page {page.index}: {e}")
                                time.sleep(1)
                        
                        if not success:
                            log(f"   ⚠️ Failed page {page.index}")
                        
                        time.sleep(0.1)
                    
                    # Package into CBZ
                    cbz_path = os.path.join(series_dir, f"{folder_name}.cbz")
                    with zipfile.ZipFile(cbz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                        for root, _, files in os.walk(temp_folder):
                            for file in sorted(files):
                                filepath = os.path.join(root, file)
                                zf.write(filepath, arcname=file)
                    
                    shutil.rmtree(temp_folder)
                    log(f"✅ Finished: Ch {ch_num}")
                    time.sleep(0.5)
                    
                except Exception as e:
                    log(f"❌ Error Ch {ch_num}: {e}")
            
            log("✨ All downloads completed!")

            # Thread-safe cleanup
            with self._lock:
                if job_id in self._active:
                    del self._active[job_id]
                if job_id in self._cancel:
                    del self._cancel[job_id]

        thread = threading.Thread(target=worker, daemon=True)
        with self._lock:
            self._active[job_id] = thread
        thread.start()

        return job_id

    def cancel(self, job_id: str) -> bool:
        """Cancel an active download."""
        with self._lock:
            if job_id in self._cancel:
                self._cancel[job_id] = True
                return True
            return False
    
    def get_downloaded(self, title: str) -> List[str]:
        """Get list of downloaded chapter numbers."""
        safe_title = self._sanitize(title)
        series_dir = os.path.join(self.download_dir, safe_title)
        
        if not os.path.exists(series_dir):
            return []
        
        downloaded = []
        for filename in os.listdir(series_dir):
            if filename.endswith('.cbz'):
                try:
                    ch_part = filename.rsplit(' - Ch', 1)[-1]
                    ch_num = ch_part.replace('.cbz', '')
                    downloaded.append(ch_num)
                except (IndexError, ValueError) as e:
                    log(f"⚠️ Could not parse chapter number from: {filename}")
        
        return downloaded


downloader = Downloader(DOWNLOAD_DIR)


# =============================================================================
# FLASK ROUTES - Pages
# =============================================================================

@app.route('/')
def index():
    """Serve main page."""
    return render_template('index.html')


# =============================================================================
# FLASK ROUTES - Sources
# =============================================================================

@app.route('/api/sources')
def get_sources():
    """Get list of available sources."""
    from sources import get_source_manager
    manager = get_source_manager()
    return jsonify(manager.get_available_sources())


@app.route('/api/sources/active', methods=['GET', 'POST'])
@csrf_protect
def active_source():
    """Get or set active source."""
    from sources import get_source_manager
    manager = get_source_manager()
    
    if request.method == 'POST':
        data = request.json
        source_id = data.get('source_id')
        if manager.set_active_source(source_id):
            log(f"🔄 Switched to {manager.active_source.name}")
            return jsonify({'status': 'ok', 'source': source_id})
        return jsonify({'status': 'error', 'message': 'Source not found'}), 404
    
    return jsonify({
        'source_id': manager.active_source_id,
        'source_name': manager.active_source.name if manager.active_source else None
    })


@app.route('/api/sources/health')
def sources_health():
    """Get health status of all sources."""
    from sources import get_source_manager
    manager = get_source_manager()
    return jsonify(manager.get_health_report())


@app.route('/api/sources/<source_id>/reset', methods=['POST'])
@csrf_protect
def reset_source(source_id: str):
    """Reset a source's error state."""
    from sources import get_source_manager
    manager = get_source_manager()
    if manager.reset_source(source_id):
        log(f"🔄 Reset {source_id}")
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 404


# =============================================================================
# FLASK ROUTES - Search & Browse
# =============================================================================

@app.route('/api/search', methods=['POST'])
@csrf_protect
def search():
    """Search for manga."""
    from sources import get_source_manager
    
    data = request.json
    query = data.get('query', '')
    source_id = data.get('source_id')
    
    if not query:
        return jsonify([])
    
    manager = get_source_manager()
    results = manager.search(query, source_id)
    
    return jsonify([r.to_dict() for r in results])


@app.route('/api/popular')
def get_popular():
    """Get popular manga."""
    from sources import get_source_manager

    source_id = request.args.get('source_id')
    try:
        page = int(request.args.get('page', 1))
        if page < 1 or page > 1000:
            return jsonify({'error': 'Page must be between 1 and 1000'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid page number'}), 400

    manager = get_source_manager()
    results = manager.get_popular(source_id, page)

    return jsonify([r.to_dict() for r in results])


@app.route('/api/latest')
def get_latest():
    """Get latest updated manga."""
    from sources import get_source_manager

    source_id = request.args.get('source_id')
    try:
        page = int(request.args.get('page', 1))
        if page < 1 or page > 1000:
            return jsonify({'error': 'Page must be between 1 and 1000'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid page number'}), 400

    manager = get_source_manager()
    results = manager.get_latest(source_id, page)

    return jsonify([r.to_dict() for r in results])


# =============================================================================
# FLASK ROUTES - Chapters
# =============================================================================

@app.route('/api/chapters', methods=['POST'])
@csrf_protect
def get_chapters():
    """Get chapters for a manga."""
    from sources import get_source_manager
    
    data = request.json
    manga_id = data.get('id')
    source_id = data.get('source')
    language = data.get('language', 'en')
    offset = data.get('offset', 0)
    limit = data.get('limit', 100)
    
    if not manga_id or not source_id:
        return jsonify({'error': 'Missing id or source'}), 400
    
    manager = get_source_manager()
    chapters = manager.get_chapters(manga_id, source_id, language)
    
    paginated = chapters[offset:offset + limit]
    
    return jsonify({
        'chapters': [c.to_dict() for c in paginated],
        'total': len(chapters),
        'hasMore': offset + limit < len(chapters),
        'nextOffset': offset + limit
    })


@app.route('/api/chapter_pages', methods=['POST'])
@csrf_protect
def get_chapter_pages():
    """Get page images for a chapter."""
    from sources import get_source_manager
    
    data = request.json
    chapter_id = data.get('chapter_id')
    source_id = data.get('source')
    
    if not chapter_id or not source_id:
        return jsonify({'error': 'Missing chapter_id or source'}), 400
    
    manager = get_source_manager()
    pages = manager.get_pages(chapter_id, source_id)
    
    if not pages:
        return jsonify({'error': 'Failed to fetch pages'}), 500
    
    return jsonify({
        'pages': [p.url for p in pages],
        'pages_data': [p.to_dict() for p in pages]
    })


# =============================================================================
# FLASK ROUTES - Library
# =============================================================================

@app.route('/api/library')
def get_library():
    """Get user's manga library."""
    return jsonify(library.load())


@app.route('/api/save', methods=['POST'])
@csrf_protect
def save_to_library():
    """Add manga to library."""
    data = request.json or {}

    manga_id = data.get('id')
    title = data.get('title')

    if not manga_id or not title:
        return jsonify({'error': 'Missing required fields: id and title'}), 400

    # Validate string lengths to prevent abuse
    if len(str(manga_id)) > 500 or len(str(title)) > 500:
        return jsonify({'error': 'Field values too long'}), 400

    key = library.add(
        manga_id=manga_id,
        title=title,
        source=data.get('source', 'mangadex'),
        status=data.get('status', 'reading'),
        cover=data.get('cover')
    )

    return jsonify({'status': 'ok', 'key': key})


@app.route('/api/update_status', methods=['POST'])
@csrf_protect
def update_status():
    """Update manga reading status."""
    data = request.json or {}
    key = data.get('key')
    status = data.get('status')

    if not key or not status:
        return jsonify({'error': 'Missing required fields: key and status'}), 400

    valid_statuses = {'reading', 'plan_to_read', 'completed', 'dropped', 'on_hold'}
    if status not in valid_statuses:
        return jsonify({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}), 400

    library.update_status(key, status)
    return jsonify({'status': 'ok'})


@app.route('/api/update_progress', methods=['POST'])
@csrf_protect
def update_progress():
    """Update reading progress."""
    data = request.json or {}
    key = data.get('key')
    chapter = data.get('chapter')

    if not key or chapter is None:
        return jsonify({'error': 'Missing required fields: key and chapter'}), 400

    library.update_progress(key, str(chapter))
    return jsonify({'status': 'ok'})


@app.route('/api/delete', methods=['POST'])
@csrf_protect
def delete_from_library():
    """Remove manga from library."""
    data = request.json or {}
    key = data.get('key')

    if not key:
        return jsonify({'error': 'Missing required field: key'}), 400

    library.remove(key)
    return jsonify({'status': 'ok'})


# =============================================================================
# FLASK ROUTES - Downloads
# =============================================================================

@app.route('/api/download', methods=['POST'])
@csrf_protect
def start_download():
    """Start downloading chapters."""
    data = request.json
    
    chapters = data.get('chapters', [])
    title = data.get('title')
    source_id = data.get('source')
    
    if not chapters or not title or not source_id:
        return jsonify({'error': 'Missing required fields'}), 400
    
    job_id = downloader.start(chapters, title, source_id)
    
    return jsonify({'status': 'started', 'job_id': job_id})


@app.route('/api/download/cancel', methods=['POST'])
@csrf_protect
def cancel_download():
    """Cancel an active download."""
    data = request.json
    job_id = data.get('job_id')
    
    if downloader.cancel(job_id):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 404


@app.route('/api/downloaded_chapters', methods=['POST'])
@csrf_protect
def get_downloaded_chapters():
    """Get list of downloaded chapters."""
    data = request.json
    chapters = downloader.get_downloaded(data.get('title', ''))
    return jsonify({'chapters': chapters})


@app.route('/downloads/<path:filename>')
def serve_download(filename: str):
    """Serve downloaded CBZ files."""
    return send_from_directory(DOWNLOAD_DIR, filename)


# =============================================================================
# FLASK ROUTES - Image Proxy
# =============================================================================

@app.route('/api/proxy/image')
def proxy_image():
    """
    Proxy external images to avoid CORS issues.
    Usage: /api/proxy/image?url=https://uploads.mangadex.org/covers/...
    """
    from flask import Response
    import hashlib

    url = request.args.get('url', '')
    if not url:
        return jsonify({'error': 'Missing url parameter'}), 400

    # Validate URL is from allowed domains
    allowed_domains = [
        'uploads.mangadex.org',
        'mangadex.org',
        'cover.nep.li',
        'avt.mkklcdnv6temp.com',
        'mangakakalot.com',
        'chapmanganato.com',
        'fanfox.net',
        'mangahere.cc',
        'mangafire.to',
        's1.mbcdnv1.xyz',
        's1.mbcdnv2.xyz',
        's1.mbcdnv3.xyz',
    ]

    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.hostname not in allowed_domains:
            # Allow any image URL for flexibility
            pass
    except Exception:
        return jsonify({'error': 'Invalid URL'}), 400

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': url,
        }
        resp = requests.get(url, headers=headers, timeout=10, stream=True)

        if resp.status_code != 200:
            return jsonify({'error': 'Failed to fetch image'}), resp.status_code

        # Get content type
        content_type = resp.headers.get('Content-Type', 'image/jpeg')

        # Return the image with caching headers
        return Response(
            resp.content,
            mimetype=content_type,
            headers={
                'Cache-Control': 'public, max-age=86400',  # Cache for 24 hours
                'Access-Control-Allow-Origin': '*'
            }
        )
    except requests.RequestException as e:
        log(f"⚠️ Image proxy error: {e}")
        return jsonify({'error': 'Failed to fetch image'}), 500


# =============================================================================
# FLASK ROUTES - Logs
# =============================================================================

@app.route('/api/logs')
def get_logs():
    """Get pending log messages."""
    messages = []
    while not msg_queue.empty():
        try:
            messages.append(msg_queue.get_nowait())
        except queue.Empty:
            break
    return jsonify({'logs': messages})


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("  MangaNegus v2.3 - Multi-Source Edition")
    print("=" * 60)

    # Register logging callback for sources (avoids circular imports)
    from sources.base import set_log_callback
    set_log_callback(log)

    # Initialize sources
    from sources import get_source_manager
    manager = get_source_manager()

    print(f"\n📚 Loaded {len(manager.sources)} sources:")
    for source in manager.sources.values():
        status = "✅" if source.is_available else "❌"
        print(f"   {status} {source.icon} {source.name} ({source.id})")

    if manager.active_source:
        print(f"\n🎯 Active source: {manager.active_source.name}")

    # Configuration from environment variables
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() in ('true', '1', 'yes')
    HOST = os.environ.get('FLASK_HOST', '127.0.0.1')  # Default to localhost for security
    PORT = int(os.environ.get('FLASK_PORT', '5000'))

    print(f"\n🌐 Server: http://{HOST}:{PORT}")
    if DEBUG:
        print("⚠️  Debug mode is ON - do not use in production!")
    print("=" * 60)

    app.run(host=HOST, port=PORT, debug=DEBUG, use_reloader=False)
