"""db -> config.json generator (pure function, easy to unit-test).

Does not depend on process.py / client.py; only maps database state ->
sing-box config.

Tag convention:
    inbound    i{id}
    selector   g{id}
    real node  n{id}
    reserved   direct / block
"""

import json
import os

from app.settings import (
    CONFIG_PATH,
    VALID_INBOUND_PROTOCOLS,
)
from app.utils import log

CLASH_API_CONTROLLER = '127.0.0.1:9090'


# ---------------------------------------------------------------------------
# Tag helpers
# ---------------------------------------------------------------------------

def _tag_inbound(iid):
    return f'i{iid}'


def _tag_selector(oid):
    return f'g{oid}'


def _tag_node(nid):
    return f'n{nid}'


def _parse_json(raw):
    """Parse a config_json / params_json field into a dict; tolerate bad input."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


# ---------------------------------------------------------------------------
# Outbounds — real nodes (n{id})
# ---------------------------------------------------------------------------

def _apply_tls(ob, cfg):
    """Attach a sing-box tls block when cfg['tls'] is truthy."""
    if not cfg.get('tls'):
        return
    tls = {'enabled': True}
    if cfg.get('sni'):
        tls['server_name'] = cfg['sni']
    if cfg.get('allowInsecure'):
        tls['insecure'] = True
    if cfg.get('alpn'):
        alpn = cfg['alpn']
        tls['alpn'] = alpn.split(',') if isinstance(alpn, str) else alpn
    ob['tls'] = tls


def _apply_transport(ob, cfg):
    """Attach a sing-box transport block for ws / h2 / grpc networks."""
    network = cfg.get('network', 'tcp') or 'tcp'
    if network == 'tcp':
        return
    transport = {'type': network}
    if network == 'ws':
        if cfg.get('ws_host'):
            transport['headers'] = {'Host': cfg['ws_host']}
        if cfg.get('ws_path'):
            transport['path'] = cfg['ws_path']
    elif network in ('h2', 'http'):
        transport['type'] = 'http'
        if cfg.get('h2_host'):
            host = cfg['h2_host']
            transport['host'] = [host] if isinstance(host, str) else host
        if cfg.get('h2_path'):
            transport['path'] = cfg['h2_path']
    elif network == 'grpc':
        if cfg.get('grpc_service_name'):
            transport['service_name'] = cfg['grpc_service_name']
    else:
        return  # unknown transport — leave outbound as plain TCP
    ob['transport'] = transport


def _build_hysteria2(tag, address, port, cfg):
    ob = {
        'type': 'hysteria2',
        'tag': tag,
        'server': address,
        'server_port': port,
        'password': cfg.get('password', ''),
        'tls': {'enabled': True, 'server_name': cfg.get('sni', '')},
    }
    if cfg.get('allowInsecure'):
        ob['tls']['insecure'] = True
    if cfg.get('alpn'):
        alpn = cfg['alpn']
        ob['tls']['alpn'] = alpn.split(',') if isinstance(alpn, str) else alpn
    if cfg.get('up_mbps'):
        ob['up_mbps'] = int(cfg['up_mbps'])
    if cfg.get('down_mbps'):
        ob['down_mbps'] = int(cfg['down_mbps'])
    if cfg.get('obfs'):
        ob['obfs'] = {'type': 'salamander', 'password': cfg.get('obfs_password', '')}
    return ob


def _build_tuic(tag, address, port, cfg):
    ob = {
        'type': 'tuic',
        'tag': tag,
        'server': address,
        'server_port': port,
        'uuid': cfg.get('uuid', ''),
        'password': cfg.get('password', ''),
        'tls': {'enabled': True, 'server_name': cfg.get('sni', '')},
    }
    if cfg.get('allowInsecure'):
        ob['tls']['insecure'] = True
    if cfg.get('alpn'):
        alpn = cfg['alpn']
        ob['tls']['alpn'] = alpn.split(',') if isinstance(alpn, str) else alpn
    if cfg.get('congestion_control'):
        ob['congestion_control'] = cfg['congestion_control']
    if cfg.get('udp_relay_mode'):
        ob['udp_relay_mode'] = cfg['udp_relay_mode']
    return ob


def _build_node_outbound(node):
    """Build a single real-node outbound n{id} from a node row/dict."""
    protocol = node['protocol']
    tag = _tag_node(node['id'])
    cfg = _parse_json(node.get('config_json'))

    if protocol == 'direct':
        return {'type': 'direct', 'tag': tag}

    address = node['address']
    port = int(node['port'])

    if protocol == 'vmess':
        ob = {
            'type': 'vmess',
            'tag': tag,
            'server': address,
            'server_port': port,
            'uuid': cfg.get('uuid') or cfg.get('id', ''),
            'alter_id': int(cfg.get('alterId', cfg.get('alter_id', 0))),
            'security': cfg.get('security', 'auto'),
        }
        _apply_tls(ob, cfg)
        _apply_transport(ob, cfg)
        return ob
    elif protocol == 'vless':
        ob = {
            'type': 'vless',
            'tag': tag,
            'server': address,
            'server_port': port,
            'uuid': cfg.get('uuid') or cfg.get('id', ''),
        }
        if cfg.get('flow'):
            ob['flow'] = cfg['flow']
        _apply_tls(ob, cfg)
        _apply_transport(ob, cfg)
        return ob
    elif protocol == 'trojan':
        ob = {
            'type': 'trojan',
            'tag': tag,
            'server': address,
            'server_port': port,
            'password': cfg.get('password', ''),
        }
        _apply_tls(ob, cfg)
        _apply_transport(ob, cfg)
        return ob
    elif protocol == 'ss':
        return {
            'type': 'shadowsocks',
            'tag': tag,
            'server': address,
            'server_port': port,
            'method': cfg.get('method', 'aes-256-gcm'),
            'password': cfg.get('password', ''),
        }
    elif protocol == 'hysteria2':
        return _build_hysteria2(tag, address, port, cfg)
    elif protocol == 'tuic':
        return _build_tuic(tag, address, port, cfg)

    raise ValueError(f'sing-box does not support protocol: {protocol}')


# ---------------------------------------------------------------------------
# Inbounds — user listeners (i{id})
# ---------------------------------------------------------------------------

def _build_inbound(inbound):
    """Build a single user inbound i{id} from an inbound row/dict."""
    protocol = inbound['protocol']
    if protocol not in VALID_INBOUND_PROTOCOLS:
        raise ValueError(f'Unsupported inbound protocol: {protocol}')

    params = _parse_json(inbound.get('params_json'))
    tag = _tag_inbound(inbound['id'])
    listen = inbound.get('listen_addr') or '0.0.0.0'
    port = int(inbound['port'])

    if protocol == 'http':
        ib = {'type': 'http', 'tag': tag, 'listen': listen, 'listen_port': port}
        user, pwd = params.get('username', ''), params.get('password', '')
        if user or pwd:
            ib['users'] = [{'username': user, 'password': pwd}]
        return ib
    elif protocol == 'socks':
        ib = {'type': 'socks', 'tag': tag, 'listen': listen, 'listen_port': port}
        user, pwd = params.get('username', ''), params.get('password', '')
        if user or pwd:
            ib['users'] = [{'username': user, 'password': pwd}]
        return ib
    elif protocol == 'ss':
        return {
            'type': 'shadowsocks',
            'tag': tag,
            'listen': listen,
            'listen_port': port,
            'method': params.get('method', 'aes-256-gcm'),
            'password': params.get('password', ''),
        }
    elif protocol == 'vmess':
        return {
            'type': 'vmess',
            'tag': tag,
            'listen': listen,
            'listen_port': port,
            'users': [{
                'uuid': params.get('uuid', ''),
                'alterId': int(params.get('alterId', 0)),
            }],
        }

    raise ValueError(f'Unsupported inbound protocol: {protocol}')


# ---------------------------------------------------------------------------
# Selectors — outbound groups (g{id})
# ---------------------------------------------------------------------------

def _build_selectors(outbounds, outbound_nodes):
    """Build a selector g{id} per outbound (id > 0), pool ordered by priority."""
    pool_by_outbound = {}
    for e in sorted(outbound_nodes, key=lambda e: (e['outbound_id'], e.get('priority', 0))):
        pool_by_outbound.setdefault(e['outbound_id'], []).append(e['node_id'])

    selectors = []
    for o in outbounds:
        oid = o['id']
        if oid == 0:
            continue  # direct sentinel — no selector
        members = [_tag_node(nid) for nid in pool_by_outbound.get(oid, [])] + ['direct']
        selectors.append({
            'type': 'selector',
            'tag': _tag_selector(oid),
            'outbounds': members,
        })
    return selectors


# ---------------------------------------------------------------------------
# Route — service inbound -> outbound mapping
# ---------------------------------------------------------------------------

def _build_route(services, inbound_ids, outbound_ids):
    rules = []
    seen_inbounds = set()
    for s in services:
        iid = s['inbound_id']
        oid = s['outbound_id']
        if iid in seen_inbounds:
            log.warning(f'service#{s["id"]}: inbound {iid} already routed, skip')
            continue
        if iid not in inbound_ids:
            log.warning(f'service#{s["id"]}: inbound {iid} not found, skip')
            continue
        if oid != 0 and oid not in outbound_ids:
            log.warning(f'service#{s["id"]}: outbound {oid} not found, skip')
            continue
        rules.append({
            'inbound': [_tag_inbound(iid)],
            'outbound': _tag_selector(oid) if oid > 0 else 'direct',
        })
        seen_inbounds.add(iid)
    return {'rules': rules, 'final': 'direct'}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_config(db_state) -> dict:
    """Build sing-box config.json content from database state (pure, no IO).

    db_state keys (assembled by the service layer from app.db.*):
        nodes          [node row]      id, protocol, address, port, config_json
        inbounds       [inbound row]   id, protocol, listen_addr, port, params_json
        outbounds      [outbound row]  id, name (id=0 is the direct sentinel)
        outbound_nodes [pool entry]    outbound_id, node_id, priority
        services       [service row]   id, name, inbound_id, outbound_id
    """
    nodes = db_state.get('nodes', [])
    inbounds = db_state.get('inbounds', [])
    outbounds = db_state.get('outbounds', [])
    outbound_nodes = db_state.get('outbound_nodes', [])
    services = db_state.get('services', [])

    node_outbounds = [_build_node_outbound(n) for n in nodes]
    selectors = _build_selectors(outbounds, outbound_nodes)
    inbound_configs = [_build_inbound(ib) for ib in inbounds]
    route = _build_route(
        services,
        {ib['id'] for ib in inbounds},
        {o['id'] for o in outbounds},
    )

    return {
        'log': {'level': 'info', 'timestamp': True},
        'inbounds': inbound_configs,
        'outbounds': node_outbounds + selectors + [
            {'type': 'direct', 'tag': 'direct'},
            {'type': 'block', 'tag': 'block'},
        ],
        'route': route,
        'experimental': {
            'clash_api': {
                'external_controller': CLASH_API_CONTROLLER,
                'secret': '',
            },
        },
    }


def write_config(config: dict) -> str:
    """Atomically write config dict to CONFIG_PATH; return path."""
    path = CONFIG_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(config, f, indent=2)
    os.replace(tmp, path)
    return path
