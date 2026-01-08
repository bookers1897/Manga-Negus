from flask import Blueprint, jsonify, request
from manganegus_app.csrf import csrf_protect
from manganegus_app.extensions import history
from manganegus_app.log import log
from .validators import validate_fields

history_bp = Blueprint('history_api', __name__, url_prefix='/api/history')


@history_bp.route('', methods=['GET'])
def get_history():
    """Return recently viewed manga (persisted across sessions)."""
    try:
        limit = int(request.args.get('limit', 50))
        if limit < 1 or limit > 200:
            return jsonify({'error': 'Limit must be between 1 and 200'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid limit'}), 400

    return jsonify(history.load(limit=limit))


@history_bp.route('', methods=['POST'])
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

    history.add(
        manga_id=data['id'],
        title=data['title'],
        source=data['source'],
        cover=data.get('cover'),
        mal_id=data.get('mal_id'),
        payload=data.get('payload') or {}
    )
    log(f"🕑 History updated: {data.get('title')}")
    return jsonify({'status': 'ok'})

