from flask import Blueprint, jsonify, request
from manganegus_app.log import log
from manganegus_app.csrf import csrf_protect
from manganegus_app.extensions import library

library_bp = Blueprint('library_api', __name__, url_prefix='/api/library')

@library_bp.route('')
def get_library():
    """Get user's manga library."""
    return jsonify(library.load())

@library_bp.route('/save', methods=['POST'])
@csrf_protect
def save_to_library():
    """Add manga to library."""
    data = request.json or {}
    manga_id = data.get('id')
    title = data.get('title')
    source = data.get('source')
    if not manga_id or not title or not source:
        return jsonify({'error': 'Missing required fields: id, title, and source'}), 400
    if len(str(manga_id)) > 500 or len(str(title)) > 500 or len(str(source)) > 100:
        return jsonify({'error': 'Field values too long'}), 400
    key = library.add(
        manga_id=manga_id,
        title=title,
        source=source,
        status=data.get('status', 'reading'),
        cover=data.get('cover')
    )
    return jsonify({'status': 'ok', 'key': key})

@library_bp.route('/update_status', methods=['POST'])
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

@library_bp.route('/update_progress', methods=['POST'])
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

@library_bp.route('/delete', methods=['POST'])
@csrf_protect
def delete_from_library():
    """Remove manga from library."""
    data = request.json or {}
    key = data.get('key')
    if not key:
        return jsonify({'error': 'Missing required field: key'}), 400
    library.remove(key)
    return jsonify({'status': 'ok'})
