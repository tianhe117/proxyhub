"""Node API routes (§4.6)."""

import threading
import uuid

from flask import Blueprint, request, jsonify

from app.db.node import list_all, list_grouped, list_by_sub, get_by_id
from app.services.node_service import (
    create_custom_node, update_node, delete_node, clear_all_nodes,
)
from app.checker import check_node
from app.utils import get_latency, update_latency
from . import auth_required

api_nodes = Blueprint('api_nodes', __name__, url_prefix='/api/nodes')


def _merge_latency(d, node_id):
    """Attach tcp/curl latency to a serialized node dict (None when unchecked)."""
    lat = get_latency(node_id)
    d['tcp_latency'] = lat.tcp_latency_ms if lat else None
    d['curl_latency'] = lat.url_latency_ms if lat else None
    return d


# ---------------------------------------------------------------------------
# Health-check task state (in-memory, async wrapper over check_node)
# ---------------------------------------------------------------------------

_check_lock = threading.Lock()
_check_tasks = {}


def _run_check_task(task_id, nodes):
    """Run check_node in the background, then persist latency to memory."""
    try:
        results = check_node(nodes)
        for nd, res in zip(nodes, results):
            _check_tasks[task_id]['nodes'][nd['id']] = {
                'tcp': {'success': res.tcp_latency_ms >= 0,
                        'latency_ms': res.tcp_latency_ms},
                'url': {'success': res.success,
                        'latency_ms': res.url_latency_ms},
            }
            _check_tasks[task_id]['checked'] += 1
            update_latency(nd['id'], res)
    finally:
        _check_tasks[task_id]['running'] = False
        _check_lock.release()


@api_nodes.route('/', methods=['GET'])
@auth_required
def list_nodes():
    return jsonify([_merge_latency(dict(n), n['id']) for n in list_all()])


@api_nodes.route('/grouped', methods=['GET'])
@auth_required
def list_nodes_grouped():
    groups = list_grouped()
    result = []
    for g in groups:
        result.append({
            'sub': dict(g['sub']) if g['sub'] else None,
            'nodes': [_merge_latency(dict(n), n['id']) for n in g['nodes']],
            'count': g['count'],
        })
    return jsonify(result)


@api_nodes.route('/by-sub/<int:sub_id>', methods=['GET'])
@auth_required
def list_nodes_by_sub(sub_id):
    return jsonify([_merge_latency(dict(n), n['id']) for n in list_by_sub(sub_id)])


@api_nodes.route('/', methods=['POST'])
@auth_required
def create_node_handler():
    data = request.get_json(force=True) or {}
    result = create_custom_node(
        data.get('name', ''), data.get('protocol', ''),
        data.get('address', ''), data.get('port', 0),
        data.get('config_json', '{}'), data.get('bin_type', 'xray')
    )
    return jsonify(result), 200 if result['success'] else 400


@api_nodes.route('/<int:node_id>', methods=['PUT'])
@auth_required
def update_node_handler(node_id):
    data = request.get_json(force=True) or {}
    result = update_node(node_id, **data)
    return jsonify(result), 200 if result['success'] else 400


@api_nodes.route('/<int:node_id>', methods=['DELETE'])
@auth_required
def delete_node_handler(node_id):
    result = delete_node(node_id)
    return jsonify(result)


@api_nodes.route('/clear', methods=['POST'])
@auth_required
def clear_nodes_handler():
    result = clear_all_nodes()
    return jsonify(result)


@api_nodes.route('/check', methods=['POST'])
@auth_required
def check_nodes_handler():
    data = request.get_json(force=True) or {}
    node_ids = data.get('node_ids')

    if not _check_lock.acquire(blocking=False):
        return jsonify({'success': False, 'message': 'A check task is already running'}), 409

    if node_ids:
        nodes = [n for n in (get_by_id(nid) for nid in node_ids) if n]
    else:
        nodes = list_all()

    if not nodes:
        _check_lock.release()
        return jsonify({'success': False, 'message': 'No nodes to check'}), 409

    task_id = str(uuid.uuid4())[:8]
    _check_tasks[task_id] = {
        'running': True,
        'total': len(nodes),
        'checked': 0,
        'nodes': {n['id']: {'tcp': None, 'url': None} for n in nodes},
    }

    threading.Thread(target=_run_check_task, args=(task_id, nodes), daemon=True).start()

    return jsonify({'success': True, 'task_id': task_id,
                    'message': f'Check started for {len(nodes)} nodes'})


@api_nodes.route('/check/<task_id>/status', methods=['GET'])
@auth_required
def check_status_handler(task_id):
    return jsonify(_check_tasks.get(task_id, {'running': False, 'message': 'Task not found'}))
