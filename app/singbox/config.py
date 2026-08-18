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

from app.settings import CONFIG_PATH, get_setting
from app.utils import log
from app.singbox import protocol

CLASH_API_IP = '127.0.0.1'


# ---------------------------------------------------------------------------
# Tag helpers
# ---------------------------------------------------------------------------

def _tag_inbound(iid):
    return f'i{iid}'


def _tag_selector(oid):
    return f'g{oid}'


def _tag_node(nid):
    return f'n{nid}'


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

    # 1. Node outbounds — delegate to protocol layer
    node_outbounds = [
        protocol.build_outbound(
            tag=_tag_node(n['id']),
            address=n['address'],
            port=n['port'],
            protocol=n['protocol'],
            config_json=n.get('config_json'),
        )
        for n in nodes
    ]

    # 2. Selector groups
    selectors = _build_selectors(outbounds, outbound_nodes)

    # 3. User inbounds — delegate to protocol layer
    inbound_configs = [
        protocol.build_inbound(
            tag=_tag_inbound(ib['id']),
            protocol=ib['protocol'],
            listen=ib.get('listen_addr') or '0.0.0.0',
            port=ib['port'],
            params_json=ib.get('params_json'),
        )
        for ib in inbounds
    ]

    # 4. Route
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
                'external_controller': f'{CLASH_API_IP}:{get_setting("clash_api_port")}',
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
