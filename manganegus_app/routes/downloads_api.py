from flask import Blueprint, jsonify, request, send_from_directory
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
    if len(chapters) > 500:
        return jsonify({'error': 'Too many chapters requested'}), 400
    if len(str(title)) > 200:
        return jsonify({'error': 'Title too long'}), 400
    job_id = downloader.start(chapters, title, source_id, manga_id)
    return jsonify({'status': 'started', 'job_id': job_id})

@downloads_bp.route('/api/download/cancel', methods=['POST'])
@csrf_protect
def cancel_download():
    """Cancel an active download."""
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')
    if downloader.cancel(job_id):
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 404

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
    """Serve downloaded CBZ files."""
    return send_from_directory(DOWNLOAD_DIR, filename)
