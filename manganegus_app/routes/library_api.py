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

    manga_id = data['id']
    source = data['source']

    # Strip source prefix from manga_id if present (prevents double-prefix bug)
    prefix = f"{source}:"
    if manga_id.startswith(prefix):
        manga_id = manga_id[len(prefix):]
        log(f"⚠️ Stripped prefix from manga_id: {data['id']} -> {manga_id}")

    key = library.add(
        manga_id=manga_id,
        title=data['title'],
        source=source,
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
    """Update reading progress (chapter + optional page)."""
    data = request.get_json(silent=True) or {}
    key = data.get('key')
    chapter = data.get('chapter', data.get('last_chapter'))
    page = data.get('page', data.get('last_page'))
    chapter_id = data.get('chapter_id')
    total_chapters = data.get('total_chapters')

    if not key or chapter is None:
        return jsonify({'error': 'Missing required fields: key and chapter'}), 400

    try:
        page = int(page) if page is not None else None
    except (ValueError, TypeError):
        page = None

    try:
        total_chapters = int(total_chapters) if total_chapters is not None else None
    except (ValueError, TypeError):
        total_chapters = None

    library.update_progress(key, str(chapter), page=page, chapter_id=chapter_id, total_chapters=total_chapters)
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
