"""Outbound API routes (§4.8)."""

from flask import Blueprint, request, jsonify

from app.models.outbound import list_all, get_by_id
from app.services.outbound_service import (
    create_outbound, update_outbound, delete_outbound,
    add_node_to_pool, remove_node_from_pool, reorder_pool, sync_pool,
)
from app.models.outbound import get_pool_nodes
from . import auth_required

api_outbounds = Blueprint('api_outbounds', __name__, url_prefix='/api/outbounds')


TYPE_ORDER = {'direct': 0, 'single': 1, 'auto': 2}

@api_outbounds.route('/', methods=['GET'])
@auth_required
def list_outbounds():
    obs = list_all()
    result = []
    for o in obs:
        d = dict(o)
        d['pool'] = [dict(p) for p in get_pool_nodes(o['id'])]
        result.append(d)
    result.sort(key=lambda x: TYPE_ORDER.get(x.get('type'), 99))
    return jsonify(result)


@api_outbounds.route('/', methods=['POST'])
@auth_required
def create_outbound_handler():
    data = request.get_json(force=True) or {}
    result = create_outbound(
        data.get('name', ''), data.get('type', 'single'),
        data.get('config_json', '{}')
    )
    return jsonify(result), 200 if result['success'] else 400


@api_outbounds.route('/<int:out_id>', methods=['PUT'])
@auth_required
def update_outbound_handler(out_id):
    data = request.get_json(force=True) or {}
    result = update_outbound(out_id, **data)
    return jsonify(result), 200 if result['success'] else 400


@api_outbounds.route('/<int:out_id>', methods=['DELETE'])
@auth_required
def delete_outbound_handler(out_id):
    result = delete_outbound(out_id)
    return jsonify(result)


@api_outbounds.route('/<int:out_id>/nodes', methods=['GET'])
@auth_required
def get_pool_nodes_handler(out_id):
    return jsonify([dict(p) for p in get_pool_nodes(out_id)])


@api_outbounds.route('/<int:out_id>/nodes', methods=['POST'])
@auth_required
def add_pool_node_handler(out_id):
    data = request.get_json(force=True) or {}
    result = add_node_to_pool(out_id, data.get('node_id', 0))
    return jsonify(result), 200 if result['success'] else 400


@api_outbounds.route('/<int:out_id>/nodes/<int:pool_id>', methods=['DELETE'])
@auth_required
def remove_pool_node_handler(out_id, pool_id):
    result = remove_node_from_pool(pool_id)
    return jsonify(result)


@api_outbounds.route('/<int:out_id>/nodes/reorder', methods=['POST'])
@auth_required
def reorder_pool_handler(out_id):
    data = request.get_json(force=True) or {}
    result = reorder_pool(out_id, data.get('order', []))
    return jsonify(result)


@api_outbounds.route('/<int:out_id>/nodes/sync', methods=['POST'])
@auth_required
def sync_pool_handler(out_id):
    data = request.get_json(force=True) or {}
    result = sync_pool(out_id, data.get('node_ids', []))
    return jsonify(result)
