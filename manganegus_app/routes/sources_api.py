from flask import Blueprint, jsonify, request
from sources import get_source_manager
from manganegus_app.log import log
from manganegus_app.csrf import csrf_protect
from .auth_api import admin_required

sources_bp = Blueprint('sources_api', __name__, url_prefix='/api/sources')

@sources_bp.route('')
def get_sources():
    """Get list of available sources."""
    manager = get_source_manager()
    return jsonify(manager.get_available_sources())

@sources_bp.route('/active', methods=['GET', 'POST'])
@admin_required
@csrf_protect
def active_source():
    """Get or set active source."""
    manager = get_source_manager()
    
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
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
@admin_required
def sources_health():
    """Get health status of all sources."""
    manager = get_source_manager()
    return jsonify(manager.get_health_report())

@sources_bp.route('/<source_id>/reset', methods=['POST'])
@admin_required
@csrf_protect
def reset_source(source_id: str):
    """Reset a source's error state."""
    manager = get_source_manager()
    if manager.reset_source(source_id):
        log(f"🔄 Reset {source_id}")
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 404


@sources_bp.route('/circuits', methods=['GET'])
def get_circuit_status():
    """
    Return circuit breaker status for all sources.

    Circuit States:
    - CLOSED: Source working, requests go through
    - OPEN: Source failing, skip for recovery_timeout seconds
    - HALF_OPEN: Testing recovery with limited requests

    Returns:
        JSON object with circuit breaker status per source:
        {
            "source_id": {
                "state": "closed|open|half_open",
                "failures": int,
                "last_failure": ISO timestamp or null,
                "retry_after": float (seconds until retry)
            }
        }
    """
    manager = get_source_manager()

    # Get all circuit breaker statuses from the registry
    result = {}
    for source_id, breaker in manager._circuit_breakers._breakers.items():
        stats = breaker.stats
        result[source_id] = {
            'state': breaker.state.value,
            'failures': stats.consecutive_failures,
            'last_failure': (
                _format_timestamp(stats.last_failure_time)
                if stats.last_failure_time > 0 else None
            ),
            'retry_after': round(breaker.retry_after, 1),
            'total_requests': stats.total_requests,
            'successful_requests': stats.successful_requests,
            'failed_requests': stats.failed_requests,
            'rejected_requests': stats.rejected_requests
        }

    return jsonify(result)


def _format_timestamp(timestamp: float) -> str:
    """Format Unix timestamp as ISO 8601 string."""
    from datetime import datetime, timezone
    if timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
