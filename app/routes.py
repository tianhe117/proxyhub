"""Flask routes — sing-box lifecycle control API.

Blueprint ``api`` with /api/* endpoints. No auth yet (deferred to the Web
layer per docs/design.md §2). CRUD routes for nodes/subscriptions/outbounds
are also deferred — this batch only wires up process control so the
"subscription → running sing-box" loop is end-to-end callable.
"""

from flask import Blueprint, jsonify

from app import services

bp = Blueprint('api', __name__)


def _json(result, status=200):
    """Wrap a service-layer dict as a JSON response."""
    return jsonify(result), status


@bp.route('/api/status', methods=['GET'])
def api_status():
    """sing-box running state + version."""
    return _json(services.get_status())


@bp.route('/api/start', methods=['POST'])
def api_start():
    """Apply config + start sing-box (restart if already running)."""
    result = services.start_singbox()
    return _json(result, 200 if result['success'] else 500)


@bp.route('/api/stop', methods=['POST'])
def api_stop():
    """Stop sing-box."""
    result = services.stop_singbox()
    return _json(result, 200 if result['success'] else 500)


@bp.route('/api/restart', methods=['POST'])
def api_restart():
    """Re-apply config + restart sing-box."""
    result = services.restart_singbox()
    return _json(result, 200 if result['success'] else 500)
