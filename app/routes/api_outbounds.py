"""Outbound API routes (§4.8)."""

from flask import Blueprint, request, jsonify

from app.db.outbound import list_all, get_by_id
from app.services.outbound_service import (
    create_outbound, update_outbound, delete_outbound,
    remove_node_from_pool, sync_pool,
)
from app.services.service_manager import switch_node
from app.db.outbound import get_pool_nodes
from app.utils import get_latency
from . import auth_required

api_outbounds = Blueprint('api_outbounds', __name__, url_prefix='/api/outbounds')


TYPE_ORDER = {'direct': 0, 'single': 1, 'auto': 2}


def _merge_latency(d, node_id):
    """Attach tcp/curl latency to a serialized pool entry (None when unchecked)."""
    lat = get_latency(node_id)
    d['tcp_latency'] = lat.tcp_latency_ms if lat else None
    d['curl_latency'] = lat.url_latency_ms if lat else None
    return d


@api_outbounds.route('/', methods=['GET'])
@auth_required
def list_outbounds():
    obs = list_all()
    result = []
    for o in obs:
        d = dict(o)
        d['pool'] = [_merge_latency(dict(p), p['node_id']) for p in get_pool_nodes(o['id'])]
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


@api_outbounds.route('/<int:out_id>/nodes/<int:pool_id>', methods=['DELETE'])
@auth_required
def remove_pool_node_handler(out_id, pool_id):
    result = remove_node_from_pool(pool_id)
    return jsonify(result)


@api_outbounds.route('/<int:out_id>/nodes/sync', methods=['POST'])
@auth_required
def sync_pool_handler(out_id):
    data = request.get_json(force=True) or {}
    result = sync_pool(out_id, data.get('node_ids', []))
    return jsonify(result)


@api_outbounds.route('/<int:out_id>/switch-node', methods=['POST'])
@auth_required
def switch_node_handler(out_id):
    data = request.get_json(force=True) or {}
    node_id = data.get('node_id', 0)
    if not node_id:
        return jsonify({'success': False, 'message': 'node_id required'}), 400
    result = switch_node(out_id, node_id)
    return jsonify(result), 200 if result['success'] else 400
