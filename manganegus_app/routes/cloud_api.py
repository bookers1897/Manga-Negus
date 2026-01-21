import json
import os
import threading
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, g
from manganegus_app.csrf import csrf_protect
from manganegus_app.log import log
from .auth_api import login_required, is_admin_user

cloud_bp = Blueprint('cloud_api', __name__, url_prefix='/api/cloud')
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
CLOUD_SYNC_FILE = os.path.join(BASE_DIR, 'instance', 'cloud_sync.json')
_lock = threading.Lock()

MAX_SYNC_ID_LENGTH = 128


def _ensure_sync_dir() -> None:
    directory = os.path.dirname(CLOUD_SYNC_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)


def _load_cloud_data() -> dict:
    if not os.path.exists(CLOUD_SYNC_FILE):
        return {}
    try:
        with open(CLOUD_SYNC_FILE, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cloud_data(data: dict) -> None:
    _ensure_sync_dir()
    with open(CLOUD_SYNC_FILE, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2)

def _is_legacy_format(data: dict) -> bool:
    if not isinstance(data, dict) or not data:
        return False
    return all(isinstance(v, dict) and 'payload' in v for v in data.values())

def _normalize_user_bucket(data: dict, user_id: str, allow_migrate: bool) -> dict:
    if _is_legacy_format(data):
        if allow_migrate:
            data = {user_id: data}
        else:
            data = {}
    if user_id not in data or not isinstance(data[user_id], dict):
        data[user_id] = {}
    return data


@cloud_bp.route('/pull')
@login_required
def pull_cloud_sync():
    sync_id = (request.args.get('sync_id') or '').strip()
    if not sync_id:
        return jsonify({'error': 'Missing sync_id'}), 400
    if len(sync_id) > MAX_SYNC_ID_LENGTH:
        return jsonify({'error': 'sync_id too long'}), 400

    user_id = str(g.current_user.id)
    allow_migrate = is_admin_user(g.current_user)
    with _lock:
        data = _load_cloud_data()
        legacy = _is_legacy_format(data)
        data = _normalize_user_bucket(data, user_id, allow_migrate)
        if legacy and allow_migrate:
            _save_cloud_data(data)
        entry = data.get(user_id, {}).get(sync_id)
    if not entry:
        return jsonify({'error': 'Sync key not found'}), 404
    return jsonify(entry)


@cloud_bp.route('/push', methods=['POST'])
@login_required
@csrf_protect
def push_cloud_sync():
    payload = request.get_json(silent=True) or {}
    sync_id = (payload.get('sync_id') or '').strip()
    data_payload = payload.get('payload')
    if not sync_id or data_payload is None:
        return jsonify({'error': 'Missing sync_id or payload'}), 400
    if len(sync_id) > MAX_SYNC_ID_LENGTH:
        return jsonify({'error': 'sync_id too long'}), 400

    entry = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'payload': data_payload
    }

    user_id = str(g.current_user.id)
    allow_migrate = is_admin_user(g.current_user)
    with _lock:
        data = _load_cloud_data()
        legacy = _is_legacy_format(data)
        data = _normalize_user_bucket(data, user_id, allow_migrate)
        if legacy and allow_migrate:
            _save_cloud_data(data)
        data[user_id][sync_id] = entry
        _save_cloud_data(data)

    log(f"☁️ Cloud sync updated for {sync_id[:8]}...")
    return jsonify({'status': 'ok', 'updated_at': entry['updated_at']})
