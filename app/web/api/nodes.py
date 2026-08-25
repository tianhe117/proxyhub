"""Node CRUD, grouping, latency, and check-task API routes."""

from flask import jsonify, request

from app.db import node as db_node
from app.services import checker
from app.web.api import bp


@bp.route('/api/nodes', methods=['GET'])
def list_nodes():
    return jsonify({'nodes': [dict(row) for row in db_node.list_all()]})


@bp.route('/api/nodes/grouped', methods=['GET'])
def list_nodes_grouped():
    groups = []
    for group in db_node.list_grouped():
        groups.append({
            'sub': dict(group['sub']) if group['sub'] else None,
            'nodes': [dict(node) for node in group['nodes']],
        })
    return jsonify({'groups': groups})


@bp.route('/api/nodes/by-sub/<int:sub_id>', methods=['GET'])
def list_nodes_by_sub(sub_id):
    return jsonify({'nodes': [dict(row) for row in db_node.list_by_sub(sub_id)]})


@bp.route('/api/nodes', methods=['POST'])
def create_node():
    data = request.get_json(force=True)
    node_id = db_node.create(
        sub_id=data.get('sub_id', 0),
        name=data['name'],
        protocol=data['protocol'],
        address=data['address'],
        port=data['port'],
        config_json=data['config_json'],
    )
    return jsonify({'success': True, 'id': node_id}), 201


@bp.route('/api/nodes/<int:node_id>', methods=['PUT'])
def update_node(node_id):
    db_node.update(node_id, **request.get_json(force=True))
    return jsonify({'success': True})


@bp.route('/api/nodes/<int:node_id>', methods=['DELETE'])
def delete_node(node_id):
    db_node.delete(node_id)
    return jsonify({'success': True})


@bp.route('/api/nodes/clear', methods=['POST'])
def clear_nodes():
    db_node.delete_all()
    return jsonify({'success': True})


@bp.route('/api/nodes/check', methods=['POST'])
def api_check_nodes():
    data = request.get_json(force=True) if request.data else {}
    result = checker.start_check(data)
    return (jsonify(result), 400) if result.get('success') is False else jsonify(result)


@bp.route('/api/nodes/check/<task_id>', methods=['GET'])
def api_check_status(task_id):
    task = checker.get_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)


def _latency_dict(result):
    if result is None:
        return None
    return {
        'tcp_latency_ms': result.tcp_latency_ms,
        'url_latency_ms': result.url_latency_ms,
        'error': result.error,
    }


@bp.route('/api/nodes/latencies', methods=['GET'])
def api_node_latencies():
    """Return a snapshot of all in-memory node latency results."""
    return jsonify({
        'latencies': {
            str(node_id): _latency_dict(result)
            for node_id, result in checker.get_all_latencies().items()
        },
    })


@bp.route('/api/nodes/<int:node_id>/latency', methods=['GET'])
def api_node_latency(node_id):
    return jsonify({
        'node_id': node_id,
        'latency': _latency_dict(checker.get_latency(node_id)),
    })
