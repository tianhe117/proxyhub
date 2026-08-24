"""Node CRUD, grouping, latency, and check-task API routes."""

import threading
import time
import uuid

from flask import jsonify, request

from app import checker
from app.db import node as db_node
from app.services.runtime import apply_config, start_singbox
from app.singbox import is_running as sb_is_running
from app.singbox import restart as sb_restart
from app.utils import get_latency
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


def _ensure_singbox_with_nodes():
    if not sb_is_running():
        start_singbox()
    else:
        apply_config()
        sb_restart()


def _resolve_node_ids(node_ids):
    result = []
    for node_id in node_ids:
        node = db_node.get_by_id(node_id)
        if node:
            result.append((node['id'], node['address'], node['port']))
    return result


def _resolve_sub_nodes(sub_id):
    return [
        (node['id'], node['address'], node['port'])
        for node in db_node.list_by_sub(sub_id)
    ]


def _resolve_all_nodes():
    return [
        (node['id'], node['address'], node['port'])
        for node in db_node.list_all()
    ]


@bp.route('/api/nodes/check', methods=['POST'])
def api_check_nodes():
    _ensure_singbox_with_nodes()
    data = request.get_json(force=True) if request.data else {}

    if 'node_id' in data:
        node_list = _resolve_node_ids([data['node_id']])
    elif 'node_ids' in data:
        node_list = _resolve_node_ids(data['node_ids'])
    elif 'sub_id' in data:
        node_list = _resolve_sub_nodes(data['sub_id'])
    else:
        node_list = _resolve_all_nodes()

    if not node_list:
        return jsonify({'success': False, 'message': 'No nodes to check'}), 400

    if len(node_list) == 1:
        node_id, address, port = node_list[0]
        result = checker.check_node(node_id, address, port)
        return jsonify({
            'single': True,
            'node_id': node_id,
            'result': {
                'tcp_latency_ms': result.tcp_latency_ms,
                'url_latency_ms': result.url_latency_ms,
                'error': result.error,
            },
        })

    task_id = f'chk_{int(time.time())}_{uuid.uuid4().hex[:6]}'
    threading.Thread(
        target=checker.check_nodes_async,
        args=(node_list, task_id),
        daemon=True,
    ).start()
    return jsonify({'task_id': task_id, 'total': len(node_list), 'status': 'running'})


@bp.route('/api/nodes/check/<task_id>', methods=['GET'])
def api_check_status(task_id):
    task = checker.get_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)


@bp.route('/api/nodes/<int:node_id>/latency', methods=['GET'])
def api_node_latency(node_id):
    result = get_latency(node_id)
    return jsonify({
        'node_id': node_id,
        'latency': {
            'tcp_latency_ms': result.tcp_latency_ms,
            'url_latency_ms': result.url_latency_ms,
            'error': result.error,
        } if result else None,
    })
