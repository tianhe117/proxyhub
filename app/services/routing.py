"""Service-level selector control."""

from app.db import outbound as db_outbound
from app.db import service as db_service
from app.singbox.clash import get_proxy_now, select_proxy
from app.utils import log


def start_service(svc_id):
    """Select the first node in a service's outbound pool."""
    svc = db_service.get_by_id(svc_id)
    if not svc:
        return {'success': False, 'message': 'Service not found'}
    outbound_id = svc['outbound_id']
    if outbound_id == 0:
        return {'success': False, 'message': 'direct outbound cannot be started'}

    pool = db_outbound.get_pool_nodes(outbound_id)
    if not pool:
        return {'success': False, 'message': 'Outbound pool is empty'}

    node_tag = f'n{pool[0]["node_id"]}'
    group_tag = f'g{outbound_id}'
    if select_proxy(group_tag, node_tag):
        log.info(f'service "{svc["name"]}" started → {node_tag}')
        return {
            'success': True,
            'message': f'Started → {node_tag}',
            'node_tag': node_tag,
        }
    log.error(f'service "{svc["name"]}" start failed: clash_api error')
    return {'success': False, 'message': 'clash_api selector switch failed'}


def stop_service(svc_id):
    """Switch a service selector to direct."""
    svc = db_service.get_by_id(svc_id)
    if not svc:
        return {'success': False, 'message': 'Service not found'}
    outbound_id = svc['outbound_id']
    if outbound_id == 0:
        return {'success': True, 'message': 'Already direct'}
    if select_proxy(f'g{outbound_id}', 'direct'):
        log.info(f'service "{svc["name"]}" stopped → direct')
        return {'success': True, 'message': 'Stopped → direct'}
    return {'success': False, 'message': 'clash_api selector switch failed'}


def restart_service(svc_id):
    """Stop then select the default node."""
    stop_result = stop_service(svc_id)
    if not stop_result['success'] and 'Already direct' not in stop_result.get('message', ''):
        return stop_result
    return start_service(svc_id)


def switch_node(svc_id, node_id):
    """Switch a service to a node that belongs to its outbound pool."""
    svc = db_service.get_by_id(svc_id)
    if not svc:
        return {'success': False, 'message': 'Service not found'}
    outbound_id = svc['outbound_id']
    if outbound_id == 0:
        return {'success': False, 'message': 'direct outbound cannot switch nodes'}

    pool = db_outbound.get_pool_nodes(outbound_id)
    pool_node_ids = {entry['node_id'] for entry in pool}
    if node_id not in pool_node_ids:
        return {'success': False, 'message': f'Node {node_id} not in outbound pool'}

    node_tag = f'n{node_id}'
    if select_proxy(f'g{outbound_id}', node_tag):
        log.info(f'service "{svc["name"]}" switched → {node_tag}')
        return {
            'success': True,
            'message': f'Switched → {node_tag}',
            'node_tag': node_tag,
        }
    return {'success': False, 'message': 'clash_api selector switch failed'}


def get_service_status(svc_id):
    """Return selector state for a service."""
    svc = db_service.get_by_id(svc_id)
    if not svc:
        return {'success': False, 'message': 'Service not found'}
    outbound_id = svc['outbound_id']
    if outbound_id == 0:
        return {'success': True, 'status': 'direct', 'current_node': 'direct'}
    now = get_proxy_now(f'g{outbound_id}')
    if now is None:
        return {'success': True, 'status': 'stopped', 'current_node': None}
    status = 'running' if now != 'direct' else 'stopped'
    return {'success': True, 'status': status, 'current_node': now}
