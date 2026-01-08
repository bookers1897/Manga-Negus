from flask import Blueprint, jsonify, request
from manganegus_app.log import log
from manganegus_app.csrf import csrf_protect
from manganegus_app.extensions import library
from .validators import validate_fields

library_bp = Blueprint('library_api', __name__, url_prefix='/api/library')

@library_bp.route('')
def get_library():
    """Get user's manga library."""
    return jsonify(library.load())

@library_bp.route('/save', methods=['POST'])
@csrf_protect
def save_to_library():
    """Add manga to library."""
    data = request.get_json(silent=True) or {}
    error = validate_fields(data, [
        ('id', str, 500),
        ('title', str, 500),
        ('source', str, 100),
    ])
    if error:
        return jsonify({'error': error}), 400
    key = library.add(
        manga_id=data['id'],
        title=data['title'],
        source=data['source'],
        status=data.get('status', 'reading'),
        cover=data.get('cover')
    )
    return jsonify({'status': 'ok', 'key': key})

@library_bp.route('/update_status', methods=['POST'])
@csrf_protect
def update_status():
    """Update manga reading status."""
    data = request.get_json(silent=True) or {}
    error = validate_fields(data, [
        ('key', str, 600),
        ('status', str, 30),
    ])
    if error:
        return jsonify({'error': error}), 400
    key = data['key']
    status = data['status']
    valid_statuses = {'reading', 'plan_to_read', 'completed', 'dropped', 'on_hold'}
    if status not in valid_statuses:
        return jsonify({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}), 400
    library.update_status(key, status)
    return jsonify({'status': 'ok'})

@library_bp.route('/update_progress', methods=['POST'])
@csrf_protect
def update_progress():
    """Update reading progress."""
    data = request.get_json(silent=True) or {}
    key = data.get('key')
    chapter = data.get('chapter', data.get('last_chapter'))
    if not key or chapter is None:
        return jsonify({'error': 'Missing required fields: key and chapter'}), 400
    library.update_progress(key, str(chapter))
    return jsonify({'status': 'ok'})

@library_bp.route('/delete', methods=['POST'])
@csrf_protect
def delete_from_library():
    """Remove manga from library."""
    data = request.get_json(silent=True) or {}
    error = validate_fields(data, [('key', str, 600)])
    if error:
        return jsonify({'error': error}), 400
    library.remove(data['key'])
    return jsonify({'status': 'ok'})
