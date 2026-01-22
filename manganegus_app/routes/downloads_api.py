import os
import tempfile
import shutil
import time
import zipfile
import requests
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Blueprint, jsonify, request, send_from_directory, abort, send_file, after_this_request, g
from manganegus_app.log import log
from manganegus_app.csrf import csrf_protect
from manganegus_app.rate_limit import limit_download, limit_light
from manganegus_app.extensions import downloader, DOWNLOAD_DIR
from manganegus_app.celery_app import is_celery_available
from .auth_api import login_required, is_admin_user
from .validators import validate_fields

# Import stealth headers for bot detection avoidance
try:
    from sources.stealth_headers import SessionFingerprint
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False
    SessionFingerprint = None

downloads_bp = Blueprint('downloads_api', __name__)

MAX_DIRECT_CHAPTERS = 25
DOWNLOAD_TOKEN_TTL = 300
_download_tokens = {}
_download_token_lock = threading.Lock()
# Parallel download workers (limited to avoid overwhelming servers)
MAX_DOWNLOAD_WORKERS = 4
# Global stealth fingerprint for consistent identity across downloads
_download_fingerprint = SessionFingerprint() if HAS_STEALTH else None


def _cleanup_download_tokens(now: float = None) -> None:
    now = now or time.time()
    expired = [token for token, entry in _download_tokens.items() if entry['expires_at'] <= now]
    for token in expired:
        _download_tokens.pop(token, None)


def _store_download_token(user_id: str, payload: dict) -> tuple[str, int]:
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time() + DOWNLOAD_TOKEN_TTL)
    with _download_token_lock:
        _cleanup_download_tokens()
        _download_tokens[token] = {
            'user_id': user_id,
            'payload': payload,
            'expires_at': expires_at
        }
    return token, expires_at


def _get_download_token_payload(user_id: str, token: str) -> dict:
    if not token:
        return {}
    with _download_token_lock:
        _cleanup_download_tokens()
        entry = _download_tokens.get(token)
        if not entry:
            return {}
        if entry['user_id'] != user_id:
            return {}
        if entry['expires_at'] <= int(time.time()):
            _download_tokens.pop(token, None)
            return {}
        return entry.get('payload') or {}


def _parse_direct_payload():
    if request.method == 'GET':
        token = (request.args.get('token') or '').strip()
        user_id = str(g.current_user.id)
        payload = _get_download_token_payload(user_id, token)
        if not payload:
            return None, (jsonify({'error': 'Invalid or expired token'}), 400)
        return payload, None

    payload = request.get_json(silent=True) or {}
    return payload, None


def _resolve_download_source(manager, source_id: str, manga_id: str, title: str) -> tuple[str, str]:
    if source_id and source_id != 'jikan':
        if manager.get_source(source_id):
            return source_id, manga_id
    if not title:
        return source_id, manga_id
    try:
        log(f"🔍 Resolving source for '{title}' (requested {source_id})...")
        results = manager.search(title, source_id=None)
    except Exception as exc:
        log(f"⚠️ Failed to resolve source: {exc}")
        return source_id, manga_id
    if results:
        best = results[0]
        return best.source, best.id
    return source_id, manga_id


@downloads_bp.route('/api/download/direct', methods=['POST', 'GET'])
@login_required
@csrf_protect
@limit_download
def direct_download():
    """Build a CBZ/ZIP on the fly and stream it to the user's device."""
    data, error_response = _parse_direct_payload()
    if error_response:
        return error_response
    error = validate_fields(data, [
        ('chapters', list, None),
        ('title', str, 200),
        ('source', str, 100),
    ])
    if error:
        return jsonify({'error': error}), 400

    chapters = data.get('chapters', [])
    source_id = data['source']
    title = data['title']
    manga_id = data.get('manga_id', '')

    if not chapters:
        return jsonify({'error': 'No chapters requested'}), 400
    if len(chapters) > MAX_DIRECT_CHAPTERS:
        return jsonify({'error': f'Too many chapters requested (max {MAX_DIRECT_CHAPTERS})'}), 400
    if len(str(title)) > 200:
        return jsonify({'error': 'Title too long'}), 400

    from sources import get_source_manager

    manager = get_source_manager()
    source = manager.get_source(source_id) if source_id and source_id != 'jikan' else None
    if not source:
        resolved_source, resolved_manga_id = _resolve_download_source(manager, source_id, manga_id, title)
        source_id = resolved_source or source_id
        if resolved_manga_id:
            manga_id = resolved_manga_id
        source = manager.get_source(source_id) if source_id else None
    if not source:
        return jsonify({'error': f"Source '{source_id}' not found"}), 404

    safe_title = downloader._sanitize(title) or 'untitled'
    temp_root = tempfile.mkdtemp(prefix='manganegus-download-')

    @after_this_request
    def cleanup(response):
        shutil.rmtree(temp_root, ignore_errors=True)
        return response

    download_session = getattr(source, 'get_download_session', None)
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

    manga_details = None
    if manga_id:
        try:
            manga_details = source.get_manga_details(manga_id)
        except Exception as e:
            log(f"⚠️ Failed to fetch manga details: {e}")

    files = []
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        ch_id = ch.get('id')
        if not ch_id:
            continue
        ch_num = str(ch.get('chapter', '0'))

        try:
            pages = source.get_pages(ch_id)
        except Exception as e:
            log(f"⚠️ Failed to fetch pages for {ch_id}: {e}")
            continue
        if not pages:
            continue

        safe_ch = downloader._sanitize_filename(ch_num)
        base_name = f"{safe_title} - Ch{safe_ch}"

        if getattr(source, 'is_file_source', False):
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
                if 'pdf' in ct:
                    ext = '.pdf'
                elif 'epub' in ct:
                    ext = '.epub'
                elif 'cbz' in ct or 'zip' in ct:
                    ext = '.cbz'
                else:
                    ext = '.bin'
            filename = downloader._sanitize_filename(f"{base_name}{ext}")
            filepath = os.path.join(temp_root, filename)
            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
            files.append(filepath)
            continue

        temp_folder = os.path.join(temp_root, base_name)
        os.makedirs(temp_folder, exist_ok=True)
        downloader._write_comic_info(temp_folder, title, ch, source, manga_details)

        def download_page(page):
            """Download a single page (runs in thread pool)."""
            try:
                # Use stealth headers for bot detection avoidance
                if _download_fingerprint:
                    headers = _download_fingerprint.get_image_headers(page.referer)
                else:
                    headers = {}
                    if page.referer:
                        headers['Referer'] = page.referer
                # Merge page-specific headers (may override some stealth headers)
                if page.headers:
                    headers.update(page.headers)
                source.wait_for_rate_limit()
                resp = download_session.get(page.url, headers=headers, timeout=20)
                if resp.status_code != 200:
                    return None
                ext = '.jpg'
                ct = resp.headers.get('Content-Type', '')
                if 'png' in ct:
                    ext = '.png'
                elif 'webp' in ct:
                    ext = '.webp'
                return (page.index, ext, resp.content)
            except Exception:
                return None

        # Download pages in parallel (rate limiter is thread-safe)
        page_results = []
        with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS) as executor:
            futures = {executor.submit(download_page, p): p for p in pages}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    page_results.append(result)

        # Write pages to disk in order
        for page_index, ext, content in sorted(page_results, key=lambda x: x[0]):
            filepath = os.path.join(temp_folder, f"{page_index:03d}{ext}")
            with open(filepath, 'wb') as f:
                f.write(content)

        cbz_name = downloader._sanitize_filename(f"{base_name}.cbz")
        cbz_path = os.path.join(temp_root, cbz_name)
        with zipfile.ZipFile(cbz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _, files_in in os.walk(temp_folder):
                for file_name in sorted(files_in):
                    zf.write(os.path.join(root, file_name), arcname=file_name)
        shutil.rmtree(temp_folder, ignore_errors=True)
        files.append(cbz_path)

    if not files:
        return jsonify({'error': 'No downloadable chapters found'}), 404

    if len(files) == 1:
        download_path = files[0]
        download_name = os.path.basename(download_path)
    else:
        bundle_name = downloader._sanitize_filename(f"{safe_title}-chapters-{int(time.time())}.zip")
        bundle_path = os.path.join(temp_root, bundle_name)
        with zipfile.ZipFile(bundle_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_path in files:
                zf.write(file_path, arcname=os.path.basename(file_path))
        download_path = bundle_path
        download_name = bundle_name

    response = send_file(download_path, as_attachment=True, download_name=download_name)
    # Prevent caches/service workers from storing direct downloads
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@downloads_bp.route('/api/download/token', methods=['POST'])
@login_required
@csrf_protect
@limit_light
def create_download_token():
    """Create a short-lived download token for direct browser downloads."""
    data = request.get_json(silent=True) or {}
    error = validate_fields(data, [
        ('chapters', list, None),
        ('title', str, 200),
        ('source', str, 100),
    ])
    if error:
        return jsonify({'error': error}), 400
    chapters = data.get('chapters', [])
    if not chapters:
        return jsonify({'error': 'No chapters requested'}), 400
    if len(chapters) > MAX_DIRECT_CHAPTERS:
        return jsonify({'error': f'Too many chapters requested (max {MAX_DIRECT_CHAPTERS})'}), 400
    user_id = str(g.current_user.id)
    token, expires_at = _store_download_token(user_id, data)
    return jsonify({'token': token, 'expires_at': expires_at})


@downloads_bp.route('/api/download', methods=['POST'])
@login_required
@csrf_protect
@limit_download
def start_download():
    """Start downloading chapters.

    When Celery/Redis is available, jobs are processed by distributed workers
    and survive server restarts. Otherwise, falls back to threading.
    """
    data = request.get_json(silent=True) or {}
    error = validate_fields(data, [
        ('chapters', list, None),
        ('title', str, 200),
        ('source', str, 100),
    ])
    if error:
        return jsonify({'error': error}), 400
    chapters = data.get('chapters', [])
    source_id = data['source']
    title = data['title']
    manga_id = data.get('manga_id', '')
    start_immediately = data.get('start_immediately', True)
    use_celery = data.get('use_celery', True)  # Allow override

    if not isinstance(start_immediately, bool):
        return jsonify({'error': 'start_immediately must be boolean'}), 400
    if len(chapters) > 500:
        return jsonify({'error': 'Too many chapters requested'}), 400
    if len(str(title)) > 200:
        return jsonify({'error': 'Title too long'}), 400

    from sources import get_source_manager

    manager = get_source_manager()
    if source_id == 'jikan' or not manager.get_source(source_id):
        resolved_source, resolved_manga_id = _resolve_download_source(manager, source_id, manga_id, title)
        source_id = resolved_source or source_id
        if resolved_manga_id:
            manga_id = resolved_manga_id

    user_id = str(g.current_user.id)

    # Use Celery if available and not explicitly disabled
    if use_celery and is_celery_available() and start_immediately:
        from manganegus_app.tasks.downloads import download_chapters_task

        user_dir = os.path.join(DOWNLOAD_DIR, downloader._sanitize_filename(user_id))
        os.makedirs(user_dir, exist_ok=True)

        # Submit task to Celery
        result = download_chapters_task.delay(
            source_id=source_id,
            manga_id=manga_id,
            manga_title=title,
            chapters=chapters,
            download_dir=user_dir
        )

        log(f"📥 Submitted Celery download job: {result.id} ({len(chapters)} chapters)")

        return jsonify({
            'status': 'started',
            'job_id': result.id,
            'backend': 'celery',
            'message': f'Queued {len(chapters)} chapters for download'
        })

    # Fallback to threading-based downloader
    job_id = downloader.add_to_queue(chapters, title, source_id, manga_id, start_immediately, user_id=user_id)
    return jsonify({
        'status': 'started',
        'job_id': job_id,
        'backend': 'threading',
        'message': 'Queued download' if start_immediately else 'Added to passive queue'
    })


@downloads_bp.route('/api/download/cancel', methods=['POST'])
@login_required
@csrf_protect
def cancel_download():
    """Cancel an active download."""
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')
    user_id = str(g.current_user.id)
    if downloader.cancel(job_id, user_id=user_id):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 404


@downloads_bp.route('/api/download/queue', methods=['GET'])
@login_required
def get_download_queue():
    """Get the current download queue status."""
    user_id = str(g.current_user.id)
    queue_data = downloader.get_queue(user_id=user_id)
    queue_data['paused'] = downloader.is_paused()
    return jsonify(queue_data)


@downloads_bp.route('/api/download/start_paused', methods=['POST'])
@login_required
@csrf_protect
def start_paused_downloads():
    """Start paused queue items."""
    data = request.get_json(silent=True) or {}
    job_ids = data.get('job_ids')
    if job_ids is not None and not isinstance(job_ids, list):
        return jsonify({'error': 'job_ids must be a list'}), 400
    user_id = str(g.current_user.id)
    downloader.start_paused_items(job_ids, user_id=user_id)
    return jsonify({'status': 'ok', 'message': 'Paused downloads started'})


@downloads_bp.route('/api/download/pause', methods=['POST'])
@login_required
@csrf_protect
def pause_download():
    """Pause downloads. Optionally specify job_id to pause specific download."""
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')  # None = pause all
    user_id = str(g.current_user.id)
    if job_id is None and not is_admin_user(g.current_user):
        return jsonify({'error': 'Admin access required'}), 403
    if downloader.pause(job_id, user_id=None if job_id is None else user_id):
        return jsonify({'status': 'ok', 'paused': True})
    return jsonify({'status': 'error'}), 404


@downloads_bp.route('/api/download/resume', methods=['POST'])
@login_required
@csrf_protect
def resume_download():
    """Resume downloads. Optionally specify job_id to resume specific download."""
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')  # None = resume all
    user_id = str(g.current_user.id)
    if job_id is None and not is_admin_user(g.current_user):
        return jsonify({'error': 'Admin access required'}), 403
    if downloader.resume(job_id, user_id=None if job_id is None else user_id):
        return jsonify({'status': 'ok', 'paused': False})
    return jsonify({'status': 'error'}), 404


@downloads_bp.route('/api/download/clear', methods=['POST'])
@login_required
@csrf_protect
def clear_completed():
    """Clear completed/cancelled/failed downloads from queue."""
    user_id = str(g.current_user.id)
    removed = downloader.clear_completed(user_id=user_id)
    return jsonify({'status': 'ok', 'removed': removed})


@downloads_bp.route('/api/download/remove', methods=['POST'])
@login_required
@csrf_protect
def remove_from_queue():
    """Remove a specific item from the queue."""
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')
    if not job_id:
        return jsonify({'error': 'job_id required'}), 400
    user_id = str(g.current_user.id)
    if downloader.remove_from_queue(job_id, user_id=user_id):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error', 'message': 'Item not found or currently downloading'}), 404


@downloads_bp.route('/api/downloaded_chapters', methods=['POST'])
@login_required
@csrf_protect
def get_downloaded_chapters():
    """Get list of downloaded chapters."""
    data = request.get_json(silent=True) or {}
    title = data.get('title')
    if not title:
        manga_id = data.get('id', '')
        title = f"manga_{str(manga_id)[:8]}" if manga_id else ''
    user_id = str(g.current_user.id)
    chapters = downloader.get_downloaded(title or '', user_id=user_id)
    return jsonify({'chapters': chapters})


@downloads_bp.route('/downloads/<path:filename>')
@login_required
def serve_download(filename: str):
    """Serve downloaded CBZ files with comprehensive path traversal protection."""
    user_id = str(g.current_user.id)
    base_dir = os.path.join(DOWNLOAD_DIR, downloader._sanitize_filename(user_id))
    # Normalize the path to prevent traversal attacks
    safe_filename = os.path.normpath(filename)

    # Block any path that tries to escape the download directory
    if safe_filename.startswith('..') or safe_filename.startswith('/') or safe_filename.startswith('\\'):
        log(f"🚨 Path traversal attempt blocked: {filename}")
        abort(403)

    # Block null bytes and other dangerous characters
    if '\0' in safe_filename or any(c in safe_filename for c in ['<', '>', '|', '\n', '\r']):
        log(f"🚨 Dangerous characters in filename: {filename}")
        abort(403)

    # Only allow CBZ and ZIP files (check BEFORE path operations)
    if not safe_filename.lower().endswith(('.cbz', '.zip')):
        log(f"⚠️ Invalid file type requested: {filename}")
        abort(403)

    # Construct full path and verify it's within DOWNLOAD_DIR
    full_path = os.path.join(base_dir, safe_filename)
    real_download_dir = os.path.realpath(base_dir)

    # Resolve path and check if file exists
    try:
        real_path = os.path.realpath(full_path)
    except (OSError, ValueError) as e:
        log(f"⚠️ Path resolution error: {filename} - {e}")
        abort(400)

    # Ensure the resolved path is within the download directory
    # Use os.path.commonpath for robust comparison across platforms
    try:
        common = os.path.commonpath([real_path, real_download_dir])
        if common != real_download_dir:
            log(f"🚨 Path escape attempt blocked: {filename} -> {real_path}")
            abort(403)
    except ValueError:
        # Paths are on different drives (Windows) or one is relative
        log(f"🚨 Invalid path comparison: {filename}")
        abort(403)

    # Verify file exists and is a regular file
    if not os.path.isfile(real_path):
        log(f"⚠️ File not found: {filename}")
        abort(404)

    return send_from_directory(real_download_dir, safe_filename)


@downloads_bp.route('/api/download/celery/status/<task_id>', methods=['GET'])
@login_required
def get_celery_job_status(task_id: str):
    """Get the status of a Celery download job.

    Args:
        task_id: Celery task ID returned from /api/download

    Returns:
        JSON with task state, progress, and result
    """
    if not is_celery_available():
        return jsonify({
            'error': 'Celery not available',
            'message': 'This endpoint requires Celery/Redis to be configured'
        }), 503

    from celery.result import AsyncResult
    from manganegus_app.celery_app import celery_app

    result = AsyncResult(task_id, app=celery_app)

    response = {
        'task_id': task_id,
        'state': result.state,
        'ready': result.ready(),
    }

    if result.state == 'PROGRESS':
        response['progress'] = result.info
    elif result.ready():
        if result.successful():
            response['result'] = result.result
        else:
            response['error'] = str(result.result)

    return jsonify(response)


@downloads_bp.route('/api/download/backend', methods=['GET'])
@login_required
def get_download_backend():
    """Get information about the download backend.

    Returns which backend is active (celery or threading) and status.
    """
    celery_available = is_celery_available()

    return jsonify({
        'backend': 'celery' if celery_available else 'threading',
        'celery_available': celery_available,
        'threading_available': True,  # Always available as fallback
        'features': {
            'persistent_queue': celery_available,
            'distributed_workers': celery_available,
            'survives_restart': celery_available,
            'progress_tracking': True,
            'pause_resume': not celery_available,  # Only threading supports pause/resume currently
        }
    })
