"""Node API routes (§4.6)."""

from flask import Blueprint, request, jsonify

from app.models.node import list_all, list_grouped, list_by_sub, get_by_id
from app.services.node_service import (
    create_custom_node, update_node, delete_node, clear_all_nodes,
)
from app.checker import check_nodes, get_check_status
from . import auth_required

api_nodes = Blueprint('api_nodes', __name__, url_prefix='/api/nodes')


@api_nodes.route('/', methods=['GET'])
@auth_required
def list_nodes():
    return jsonify([dict(n) for n in list_all()])


@api_nodes.route('/grouped', methods=['GET'])
@auth_required
def list_nodes_grouped():
    groups = list_grouped()
    result = []
    for g in groups:
        result.append({
            'sub': dict(g['sub']) if g['sub'] else None,
            'nodes': [dict(n) for n in g['nodes']],
            'count': g['count'],
        })
    return jsonify(result)


@api_nodes.route('/by-sub/<int:sub_id>', methods=['GET'])
@auth_required
def list_nodes_by_sub(sub_id):
    return jsonify([dict(n) for n in list_by_sub(sub_id)])


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
    ctype = data.get('check_type', 'both')
    result = check_nodes(node_ids, ctype)
    return jsonify(result), 200 if result.get('success') else 409


@api_nodes.route('/check/<task_id>/status', methods=['GET'])
@auth_required
def check_status_handler(task_id):
    return jsonify(get_check_status(task_id))
