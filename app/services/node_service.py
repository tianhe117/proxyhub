"""Node management and validation service."""

import json

from app.models.node import (
    create, update, delete, get_by_id, list_all as list_nodes,
    list_grouped, list_by_sub,
)
from app.utils.validators import is_valid_protocol, is_valid_port


def create_custom_node(name, protocol, address, port, config_json, bin_type='xray'):
    """Create a custom (non-subscription) node after validation.

    Returns:
        dict: {success, message, node_id}
    """
    if not name or not name.strip():
        return {'success': False, 'message': 'Name is required'}
    if not is_valid_protocol(protocol):
        return {'success': False, 'message': f'Invalid protocol: {protocol}'}
    if not is_valid_port(port):
        return {'success': False, 'message': f'Invalid port: {port}'}
    if not address or not address.strip():
        return {'success': False, 'message': 'Address is required'}

    if isinstance(config_json, str):
        try:
            config_json = json.loads(config_json)
        except json.JSONDecodeError:
            return {'success': False, 'message': 'config_json is not valid JSON'}

    node_id = create(0, name.strip(), protocol, address.strip(),
                     int(port), config_json, bin_type)
    return {'success': True, 'message': 'Node created', 'node_id': node_id}


def update_node(node_id, **fields):
    """Update a node after basic validation."""
    node = get_by_id(node_id)
    if not node:
        return {'success': False, 'message': 'Node not found'}

    if 'protocol' in fields and not is_valid_protocol(fields['protocol']):
        return {'success': False, 'message': f'Invalid protocol: {fields["protocol"]}'}
    if 'port' in fields and not is_valid_port(fields['port']):
        return {'success': False, 'message': f'Invalid port: {fields["port"]}'}

    update(node_id, **fields)
    return {'success': True, 'message': 'Node updated'}


def delete_node(node_id):
    """Delete a node."""
    node = get_by_id(node_id)
    if not node:
        return {'success': False, 'message': 'Node not found'}
    delete(node_id)
    return {'success': True, 'message': 'Node deleted'}


def clear_all_nodes():
    """Delete all nodes."""
    from app.models.node import delete_all
    delete_all()
    return {'success': True, 'message': 'All nodes cleared'}
