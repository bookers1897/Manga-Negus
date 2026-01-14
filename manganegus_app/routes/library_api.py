from flask import Blueprint, jsonify, request
import json
import os
from manganegus_app.log import log
from manganegus_app.csrf import csrf_protect
from manganegus_app.extensions import library
from .validators import validate_fields

library_bp = Blueprint('library_api', __name__, url_prefix='/api/library')
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PREFERENCES_FILE = os.path.join(BASE_DIR, 'instance', 'preferences.json')

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
    page_total = data.get('page_total')

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

    try:
        page_total = int(page_total) if page_total is not None else None
    except (ValueError, TypeError):
        page_total = None

    library.update_progress(
        key,
        str(chapter),
        page=page,
        chapter_id=chapter_id,
        total_chapters=total_chapters,
        page_total=page_total
    )
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

@library_bp.route('/export')
def export_library():
    """Export library as JSON."""
    return jsonify(library.load())

@library_bp.route('/import', methods=['POST'])
@csrf_protect
def import_library():
    """Import library entries from JSON payload."""
    data = request.get_json(silent=True) or {}
    entries = data.get('entries') if isinstance(data, dict) else data
    if isinstance(entries, dict):
        entries = list(entries.values())
    if not isinstance(entries, list):
        return jsonify({'error': 'Invalid import payload'}), 400

    imported = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = entry.get('key', '')
        source = entry.get('source')
        manga_id = entry.get('manga_id') or entry.get('id')
        title = entry.get('title')
        cover = entry.get('cover')
        status = entry.get('status', 'reading')

        if key and ':' in key and (not source or not manga_id):
            source, manga_id = key.split(':', 1)

        if not (source and manga_id and title):
            continue

        key = library.add(manga_id=manga_id, title=title, source=source, status=status, cover=cover)
        last_chapter = entry.get('last_chapter') or entry.get('last_chapter_read')
        last_page = entry.get('last_page') or entry.get('last_page_read')
        last_chapter_id = entry.get('last_chapter_id')
        total_chapters = entry.get('total_chapters')
        page_total = entry.get('last_page_total')
        if last_chapter is not None:
            library.update_progress(
                key,
                str(last_chapter),
                page=last_page,
                chapter_id=last_chapter_id,
                total_chapters=total_chapters,
                page_total=page_total
            )
        imported += 1

    return jsonify({'status': 'ok', 'imported': imported})


def _ensure_preferences_dir() -> None:
    directory = os.path.dirname(PREFERENCES_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)


@library_bp.route('/preferences', methods=['GET'])
def get_preferences():
    """Get saved user preferences (local sync)."""
    if not os.path.exists(PREFERENCES_FILE):
        return jsonify({})
    try:
        with open(PREFERENCES_FILE, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        return jsonify(data if isinstance(data, dict) else {})
    except (OSError, json.JSONDecodeError):
        return jsonify({})


@library_bp.route('/preferences', methods=['POST'])
@csrf_protect
def save_preferences():
    """Persist user preferences (local sync)."""
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid preferences payload'}), 400
    _ensure_preferences_dir()
    try:
        with open(PREFERENCES_FILE, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, indent=2)
        return jsonify({'status': 'ok'})
    except OSError as exc:
        return jsonify({'error': str(exc)}), 500
