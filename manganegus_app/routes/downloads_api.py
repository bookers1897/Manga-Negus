import os
from flask import Blueprint, jsonify, request, send_from_directory, abort
from werkzeug.utils import secure_filename
from manganegus_app.log import log
from manganegus_app.csrf import csrf_protect
from manganegus_app.extensions import downloader, DOWNLOAD_DIR
from .validators import validate_fields

downloads_bp = Blueprint('downloads_api', __name__)

@downloads_bp.route('/api/download', methods=['POST'])
@csrf_protect
def start_download():
    """Start downloading chapters."""
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
    if not isinstance(start_immediately, bool):
        return jsonify({'error': 'start_immediately must be boolean'}), 400
    if len(chapters) > 500:
        return jsonify({'error': 'Too many chapters requested'}), 400
    if len(str(title)) > 200:
        return jsonify({'error': 'Title too long'}), 400
    job_id = downloader.add_to_queue(chapters, title, source_id, manga_id, start_immediately)
    return jsonify({
        'status': 'started',
        'job_id': job_id,
        'message': 'Queued download' if start_immediately else 'Added to passive queue'
    })

@downloads_bp.route('/api/download/cancel', methods=['POST'])
@csrf_protect
def cancel_download():
    """Cancel an active download."""
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')
    if downloader.cancel(job_id):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 404


@downloads_bp.route('/api/download/queue', methods=['GET'])
def get_download_queue():
    """Get the current download queue status."""
    queue_data = downloader.get_queue()
    queue_data['paused'] = downloader.is_paused()
    return jsonify(queue_data)


@downloads_bp.route('/api/download/start_paused', methods=['POST'])
@csrf_protect
def start_paused_downloads():
    """Start paused queue items."""
    data = request.get_json(silent=True) or {}
    job_ids = data.get('job_ids')
    if job_ids is not None and not isinstance(job_ids, list):
        return jsonify({'error': 'job_ids must be a list'}), 400
    downloader.start_paused_items(job_ids)
    return jsonify({'status': 'ok', 'message': 'Paused downloads started'})


@downloads_bp.route('/api/download/pause', methods=['POST'])
@csrf_protect
def pause_download():
    """Pause downloads. Optionally specify job_id to pause specific download."""
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')  # None = pause all
    if downloader.pause(job_id):
        return jsonify({'status': 'ok', 'paused': True})
    return jsonify({'status': 'error'}), 404


@downloads_bp.route('/api/download/resume', methods=['POST'])
@csrf_protect
def resume_download():
    """Resume downloads. Optionally specify job_id to resume specific download."""
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')  # None = resume all
    if downloader.resume(job_id):
        return jsonify({'status': 'ok', 'paused': False})
    return jsonify({'status': 'error'}), 404


@downloads_bp.route('/api/download/clear', methods=['POST'])
@csrf_protect
def clear_completed():
    """Clear completed/cancelled/failed downloads from queue."""
    removed = downloader.clear_completed()
    return jsonify({'status': 'ok', 'removed': removed})


@downloads_bp.route('/api/download/remove', methods=['POST'])
@csrf_protect
def remove_from_queue():
    """Remove a specific item from the queue."""
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')
    if not job_id:
        return jsonify({'error': 'job_id required'}), 400
    if downloader.remove_from_queue(job_id):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error', 'message': 'Item not found or currently downloading'}), 404

@downloads_bp.route('/api/downloaded_chapters', methods=['POST'])
@csrf_protect
def get_downloaded_chapters():
    """Get list of downloaded chapters."""
    data = request.get_json(silent=True) or {}
    title = data.get('title')
    if not title:
        manga_id = data.get('id', '')
        title = f"manga_{str(manga_id)[:8]}" if manga_id else ''
    chapters = downloader.get_downloaded(title or '')
    return jsonify({'chapters': chapters})

@downloads_bp.route('/downloads/<path:filename>')
def serve_download(filename: str):
    """Serve downloaded CBZ files with comprehensive path traversal protection."""
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
    full_path = os.path.join(DOWNLOAD_DIR, safe_filename)
    real_download_dir = os.path.realpath(DOWNLOAD_DIR)

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

    return send_from_directory(DOWNLOAD_DIR, safe_filename)
