"""Outbound and node-pool management service."""

import json

from app.models.outbound import (
    create as create_ob, update as update_ob, delete as delete_ob,
    get_by_id as get_ob, add_pool_node, remove_pool_node, reorder_pool_nodes,
    get_pool_nodes, sync_pool_nodes,
)
from app.models.node import get_by_id as get_node


def create_outbound(name, out_type, config_json=None):
    """Create an outbound (single, auto, or direct)."""
    if not name or not name.strip():
        return {'success': False, 'message': 'Name is required'}
    if out_type not in ('single', 'auto', 'direct'):
        return {'success': False, 'message': 'Type must be "single", "auto", or "direct"'}

    if config_json is None:
        config_json = {}
    if isinstance(config_json, str):
        try:
            config_json = json.loads(config_json)
        except json.JSONDecodeError:
            return {'success': False, 'message': 'config_json is not valid JSON'}

    ob_id = create_ob(name.strip(), out_type, config_json)
    return {'success': True, 'message': 'Outbound created', 'outbound_id': ob_id}


def update_outbound(out_id, **fields):
    """Update an outbound."""
    ob = get_ob(out_id)
    if not ob:
        return {'success': False, 'message': 'Outbound not found'}
    update_ob(out_id, **fields)
    return {'success': True, 'message': 'Outbound updated'}


def delete_outbound(out_id):
    """Delete an outbound and its pool nodes."""
    ob = get_ob(out_id)
    if not ob:
        return {'success': False, 'message': 'Outbound not found'}
    delete_ob(out_id)
    return {'success': True, 'message': 'Outbound deleted'}


def add_node_to_pool(outbound_id, node_id):
    """Add a node to an outbound pool."""
    ob = get_ob(outbound_id)
    if not ob:
        return {'success': False, 'message': 'Outbound not found'}

    node = get_node(node_id)
    if not node:
        return {'success': False, 'message': 'Node not found'}

    # Check duplicate
    pool = get_pool_nodes(outbound_id)
    if any(p['node_id'] == node_id for p in pool):
        return {'success': False, 'message': 'Node already in pool'}

    pool_id = add_pool_node(outbound_id, node_id)
    return {'success': True, 'message': 'Node added to pool', 'pool_id': pool_id}


def remove_node_from_pool(pool_id):
    """Remove a pool entry."""
    remove_pool_node(pool_id)
    return {'success': True, 'message': 'Node removed from pool'}


def reorder_pool(outbound_id, node_order):
    """Reorder pool nodes. *node_order* is a list of pool entry IDs."""
    reorder_pool_nodes(outbound_id, node_order)
    return {'success': True, 'message': 'Pool reordered'}


def sync_pool(outbound_id, node_ids):
    """Replace all pool nodes with the given node_ids list."""
    ob = get_ob(outbound_id)
    if not ob:
        return {'success': False, 'message': 'Outbound not found'}
    sync_pool_nodes(outbound_id, node_ids)
    return {'success': True, 'message': 'Pool synced'}
