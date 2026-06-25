"""Service configuration generator (§15).

Translates database entities (service/inbound/outbound/node) into
JSON config files for the proxy binaries.
"""

import json
import os
import random
import socket

from app.models.service import get_by_id as get_service
from app.models.inbound import get_by_id as get_inbound
from app.models.outbound import get_by_id as get_outbound, get_pool_nodes
from app.models.node import get_by_id as get_node
from app.engine import build_outbound_config, get_exe
from app.engine.xray import build_xray_inbound
from app.settings import SOCKS_PORT_START, SOCKS_PORT_END
from app.logger import log


def is_port_available(port, host='127.0.0.1'):
    """Check if a TCP port is available by attempting to bind."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.close()
        return True
    except OSError:
        return False


def find_available_port(start=SOCKS_PORT_START, end=SOCKS_PORT_END, exclude=None):
    """Randomly find an available port in [start, end], avoiding *exclude*."""
    exclude = exclude or set()
    attempts = 100
    for _ in range(attempts):
        port = random.randint(start, end)
        if port in exclude:
            continue
        if is_port_available(port):
            return port
    raise RuntimeError(f'No available port found in range {start}-{end}')


def check_inbound_port(port):
    """Check if the inbound port is available.  Returns (ok, error_msg)."""
    if not is_port_available(port, '0.0.0.0'):
        return False, f'Port {port} is already in use'
    return True, ''


def get_outbound_node(outbound, node_id=None):
    """Resolve the node that an outbound points to.

    - single: config_json.node_id → node row
    - auto: first pool entry (lowest priority) → node row, unless node_id overrides
    - direct: virtual node (freedom protocol, no remote server)

    Args:
        outbound: outbound row
        node_id: override node ID (used by failover to pick a specific node)
    """
    cfg = outbound['config_json']
    if isinstance(cfg, str):
        cfg = json.loads(cfg)

    if outbound['type'] == 'direct':
        return {
            'id': 0, 'name': 'Direct', 'protocol': 'direct',
            'address': '', 'port': 0,
            'config_json': '{}', 'bin_type': 'xray',
        }
    elif outbound['type'] == 'single':
        nid = cfg.get('node_id') if isinstance(cfg, dict) else json.loads(cfg).get('node_id')
        return get_node(nid)
    else:
        # auto — use node_id override if provided, otherwise first pool entry
        if node_id:
            return get_node(node_id)
        out_id = outbound['id']
        pool = get_pool_nodes(out_id)
        if not pool:
            return None
        return get_node(pool[0]['node_id'])


def generate_service_config(service_id):
    """Generate configuration dicts for a service.

    Returns:
        dict with keys: success, message, service_name, config_dir,
                        xray_in, outbound_bin, outbound_config,
                        socks_port, inbound_port, node_name
    """
    svc = get_service(service_id)
    if not svc:
        return {'success': False, 'message': 'Service not found'}

    inbound = get_inbound(svc['inbound_id'])
    if not inbound:
        return {'success': False, 'message': 'Inbound not found'}

    outbound = get_outbound(svc['outbound_id'])
    if not outbound:
        return {'success': False, 'message': 'Outbound not found'}

    node = get_outbound_node(outbound)
    if not node:
        return {'success': False, 'message': 'No node available for outbound'}

    # Check inbound port
    ok, err = check_inbound_port(inbound['port'])
    if not ok:
        return {'success': False, 'message': err}

    # Allocate SOCKS5 port
    socks_port = find_available_port()

    # Build Xray inbound config
    xray_in = build_xray_inbound(inbound, socks_port)

    # Build outbound config
    outbound_config, _filename = build_outbound_config(node, socks_port)
    bin_type = node['bin_type']

    service_name = svc['name']
    config_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'config', service_name
    )

    return {
        'success':        True,
        'service_name':   service_name,
        'config_dir':     config_dir,
        'xray_in':        xray_in,
        'outbound_bin':   bin_type,
        'outbound_config': outbound_config,
        'socks_port':     socks_port,
        'inbound_port':   inbound['port'],
        'node_name':      node['name'],
    }


def save_service_config(service_name, xray_in, outbound_bin, outbound_config):
    """Write configuration files to config/<service_name>/.

    Creates:
        config/<service_name>/xray_in.json
        config/<service_name>/<bin_type>_out.json
    """
    config_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'config', service_name
    )
    os.makedirs(config_dir, exist_ok=True)

    # Xray inbound config
    xray_in_path = os.path.join(config_dir, 'xray_in.json')
    with open(xray_in_path, 'w') as f:
        json.dump(xray_in, f, indent=2)

    # Outbound config
    out_name = f'{outbound_bin}_out.json'
    out_path = os.path.join(config_dir, out_name)
    with open(out_path, 'w') as f:
        json.dump(outbound_config, f, indent=2)

    log('info', 'config', f'Saved: {xray_in_path}, {out_path}')
    return xray_in_path, out_path
