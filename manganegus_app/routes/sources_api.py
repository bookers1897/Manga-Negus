from flask import Blueprint, jsonify, request
from sources import get_source_manager
from manganegus_app.log import log
from manganegus_app.csrf import csrf_protect

sources_bp = Blueprint('sources_api', __name__, url_prefix='/api/sources')

@sources_bp.route('')
def get_sources():
    """Get list of available sources."""
    manager = get_source_manager()
    return jsonify(manager.get_available_sources())

@sources_bp.route('/active', methods=['GET', 'POST'])
@csrf_protect
def active_source():
    """Get or set active source."""
    manager = get_source_manager()
    
    if request.method == 'POST':
        data = request.json
        source_id = data.get('source_id')
        if manager.set_active_source(source_id):
            log(f"🔄 Switched to {manager.active_source.name}")
            return jsonify({'status': 'ok', 'source': source_id})
        return jsonify({'status': 'error', 'message': 'Source not found'}), 404
    
    return jsonify({
        'source_id': manager.active_source_id,
        'source_name': manager.active_source.name if manager.active_source else None
    })

@sources_bp.route('/health')
def sources_health():
    """Get health status of all sources."""
    manager = get_source_manager()
    return jsonify(manager.get_health_report())

@sources_bp.route('/<source_id>/reset', methods=['POST'])
@csrf_protect
def reset_source(source_id: str):
    """Reset a source's error state."""
    manager = get_source_manager()
    if manager.reset_source(source_id):
        log(f"🔄 Reset {source_id}")
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 404
