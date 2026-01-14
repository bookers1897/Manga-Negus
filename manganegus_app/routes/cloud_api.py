import json
import os
import threading
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from manganegus_app.csrf import csrf_protect
from manganegus_app.log import log

cloud_bp = Blueprint('cloud_api', __name__, url_prefix='/api/cloud')
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
CLOUD_SYNC_FILE = os.path.join(BASE_DIR, 'instance', 'cloud_sync.json')
_lock = threading.Lock()


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


@cloud_bp.route('/pull')
def pull_cloud_sync():
    sync_id = (request.args.get('sync_id') or '').strip()
    if not sync_id:
        return jsonify({'error': 'Missing sync_id'}), 400

    with _lock:
        data = _load_cloud_data()
        entry = data.get(sync_id)
    if not entry:
        return jsonify({'error': 'Sync key not found'}), 404
    return jsonify(entry)


@cloud_bp.route('/push', methods=['POST'])
@csrf_protect
def push_cloud_sync():
    payload = request.get_json(silent=True) or {}
    sync_id = (payload.get('sync_id') or '').strip()
    data_payload = payload.get('payload')
    if not sync_id or data_payload is None:
        return jsonify({'error': 'Missing sync_id or payload'}), 400

    entry = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'payload': data_payload
    }

    with _lock:
        data = _load_cloud_data()
        data[sync_id] = entry
        _save_cloud_data(data)

    log(f"☁️ Cloud sync updated for {sync_id[:8]}...")
    return jsonify({'status': 'ok', 'updated_at': entry['updated_at']})
