from flask import Blueprint, jsonify, request, g
from manganegus_app.csrf import csrf_protect
from manganegus_app.extensions import history
from manganegus_app.log import log
from .auth_api import login_required
from .validators import validate_fields

history_bp = Blueprint('history_api', __name__, url_prefix='/api/history')


@history_bp.route('', methods=['GET'])
@login_required
def get_history():
    """Return recently viewed manga (persisted across sessions)."""
    try:
        limit = int(request.args.get('limit', 50))
        if limit < 1 or limit > 200:
            return jsonify({'error': 'Limit must be between 1 and 200'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid limit'}), 400

    user_id = str(g.current_user.id)
    return jsonify(history.load(user_id=user_id, limit=limit))


@history_bp.route('', methods=['POST'])
@login_required
@csrf_protect
def add_history():
    """Add or bump a history entry."""
    data = request.get_json(silent=True) or {}
    error = validate_fields(data, [
        ('id', str, 500),
        ('title', str, 500),
        ('source', str, 100),
    ])
    if error:
        return jsonify({'error': error}), 400

    user_id = str(g.current_user.id)
    history.add(
        user_id=user_id,
        manga_id=data['id'],
        title=data['title'],
        source=data['source'],
        cover=data.get('cover'),
        mal_id=data.get('mal_id'),
        payload=data.get('payload') or {}
    )
    log(f"🕑 History updated: {data.get('title')}")
    return jsonify({'status': 'ok'})


@history_bp.route('/import', methods=['POST'])
@login_required
@csrf_protect
def import_history():
    """Import history entries from backup."""
    data = request.get_json(silent=True) or {}
    entries = data.get('entries') if isinstance(data, dict) else data
    if isinstance(entries, dict):
        entries = list(entries.values())
    if not isinstance(entries, list):
        return jsonify({'error': 'Invalid history import payload'}), 400

    imported = 0
    user_id = str(g.current_user.id)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        manga_id = entry.get('id') or entry.get('manga_id')
        title = entry.get('title')
        source = entry.get('source')
        if not (manga_id and title and source):
            continue
        history.add(
            user_id=user_id,
            manga_id=manga_id,
            title=title,
            source=source,
            cover=entry.get('cover'),
            mal_id=entry.get('mal_id'),
            payload=entry.get('payload') or {}
        )
        imported += 1

    return jsonify({'status': 'ok', 'imported': imported})
