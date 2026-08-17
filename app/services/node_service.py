"""Node management and validation service."""

import json

from app.db.node import create, update, delete, delete_all, get_by_id
from app.db.outbound import get_by_id as get_outbound
from app.db.references import list_incoming_references
from app.db.database import get_db
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
    """Delete a node, refusing if an outbound references it.

    TODO(upper-layer): 删除策略待定——现「拒绝删除」与外键 CASCADE 冲突，
    上层重写时决定去留（静默级联 或 前端确认弹窗）。
    """
    node = get_by_id(node_id)
    if not node:
        return {'success': False, 'message': 'Node not found'}

    refs = list_incoming_references(get_db(), 'nodes', node_id)
    if refs:
        ob_ids = sorted({row['outbound_id'] for ref in refs for row in ref['rows']})
        names = ', '.join(
            (get_outbound(oid) or {'name': f'#{oid}'})['name'] for oid in ob_ids
        )
        return {'success': False,
                'message': f'Node is used by outbound(s): {names}'}

    delete(node_id)
    return {'success': True, 'message': 'Node deleted'}


def clear_all_nodes():
    """Delete all nodes."""
    delete_all()
    return {'success': True, 'message': 'All nodes cleared'}
