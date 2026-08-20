"""Clash YAML subscription parser.

Parses the ``proxies:`` block of a Clash config into node dicts. The YAML
key names (cipher / servername / skip-cert-verify / ws-opts / ...) are mapped
to the v2 config_json keys consumed by app.singbox.protocol.

Unsupported v2 types (ssr / anytls) are skipped with a log.warning.
"""

import json

import yaml

from app.utils import log


def parse_yaml(text):
    """Parse Clash YAML text into a list of node dicts.

    Returns an empty list on YAML error (after attempting a fallback block
    extraction).
    """
    try:
        data = yaml.safe_load(text)
        proxies = data.get('proxies', []) if isinstance(data, dict) else []
    except yaml.YAMLError:
        proxies = _extract_proxies_block(text)

    nodes = []
    for p in proxies or []:
        if not isinstance(p, dict):
            continue
        node = _parse_proxy(p)
        if node:
            nodes.append(node)
    return nodes


def _extract_proxies_block(text):
    """Recover the ``proxies:`` block from a malformed YAML."""
    lines = text.splitlines()
    in_proxies = False
    block = []
    for line in lines:
        if not in_proxies:
            if line.strip().startswith('proxies:'):
                in_proxies = True
                continue
        else:
            # Stop at next top-level key
            if line and not line[0].isspace() and not line.strip().startswith('-'):
                if ':' in line:
                    break
            block.append(line)
    try:
        loaded = yaml.safe_load('\n'.join(block))
        return loaded or []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Per-protocol parsers
# ---------------------------------------------------------------------------

def _parse_proxy(p):
    ptype = str(p.get('type', '')).lower()
    name = p.get('name', 'Unnamed')
    server = p.get('server', '')
    try:
        port = int(p.get('port', 0))
    except (TypeError, ValueError):
        log.warning(f'clash proxy "{name}": bad port {p.get("port")!r}, skip')
        return None

    if ptype == 'ss':
        return _parse_ss(name, server, port, p)
    if ptype == 'vmess':
        return _parse_vmess(name, server, port, p)
    if ptype == 'vless':
        return _parse_vless(name, server, port, p)
    if ptype == 'trojan':
        return _parse_trojan(name, server, port, p)
    if ptype in ('hysteria2', 'hy2', 'hysteria'):
        return _parse_hysteria2(name, server, port, p)
    if ptype == 'tuic':
        return _parse_tuic(name, server, port, p)
    # ssr / anytls / unknown — v2 protocol surface dropped these
    log.warning(f'clash proxy "{name}": unsupported type "{ptype}", skip')
    return None


def _parse_ss(name, server, port, p):
    config = {
        'method': p.get('cipher', 'aes-256-gcm'),
        'password': p.get('password', ''),
    }
    plugin = p.get('plugin', '')
    if plugin == 'obfs':
        popts = p.get('plugin-opts', {}) or {}
        config['plugin'] = 'obfs-local'
        mode = popts.get('mode', 'http')
        host = popts.get('host', '')
        opts = f'obfs={mode}'
        if host:
            opts += f';obfs-host={host}'
        config['plugin_opts'] = opts
    return _node(name, 'ss', server, port, config)


def _parse_vmess(name, server, port, p):
    network = p.get('network', 'tcp')
    config = {
        'uuid': p.get('uuid', ''),
        'alterId': int(p.get('alterId', 0)),
        'security': p.get('cipher', 'auto'),
        'network': network,
        'tls': bool(p.get('tls', False)),
        'sni': p.get('servername', p.get('sni', '')),
        'allowInsecure': p.get('skip-cert-verify', False),
        'fingerprint': p.get('fingerprint', ''),
    }
    _apply_transport(config, p, network)
    return _node(name, 'vmess', server, port, config)


def _parse_vless(name, server, port, p):
    network = p.get('network', 'tcp')
    config = {
        'uuid': p.get('uuid', ''),
        'flow': p.get('flow', ''),
        'encryption': p.get('encryption', 'none'),
        'network': network,
        'tls': bool(p.get('tls', False)),
        'sni': p.get('servername', p.get('sni', '')),
        'allowInsecure': p.get('skip-cert-verify', False),
        'fingerprint': p.get('fingerprint', ''),
    }
    # reality-opts
    reality = p.get('reality-opts', {})
    if reality:
        if reality.get('public-key'):
            config['reality_public_key'] = reality['public-key']
        if reality.get('short-id'):
            config['reality_short_id'] = reality['short-id']
    _apply_transport(config, p, network)
    return _node(name, 'vless', server, port, config)


def _parse_trojan(name, server, port, p):
    network = p.get('network', 'tcp')
    alpn = p.get('alpn')
    config = {
        'password': p.get('password', ''),
        'sni': p.get('sni', p.get('servername', '')),
        'alpn': ','.join(alpn) if isinstance(alpn, list) else (alpn or ''),
        'allowInsecure': p.get('skip-cert-verify', False),
        'network': network,
        'tls': True,
        'fingerprint': p.get('fingerprint', ''),
    }
    _apply_transport(config, p, network)
    return _node(name, 'trojan', server, port, config)


def _parse_hysteria2(name, server, port, p):
    config = {
        'password': p.get('password', p.get('auth', '')),
        'sni': p.get('sni', p.get('servername', '')),
        'allowInsecure': p.get('skip-cert-verify', False),
    }
    alpn = p.get('alpn')
    if alpn:
        config['alpn'] = ','.join(alpn) if isinstance(alpn, list) else alpn
    # up/down appear under several keys across clash dialects
    if p.get('up'):
        config['up_mbps'] = _to_int(p['up'])
    elif p.get('up_mbps'):
        config['up_mbps'] = _to_int(p['up_mbps'])
    if p.get('down'):
        config['down_mbps'] = _to_int(p['down'])
    elif p.get('down_mbps'):
        config['down_mbps'] = _to_int(p['down_mbps'])
    if p.get('obfs'):
        config['obfs'] = p['obfs']
    if p.get('obfs-password'):
        config['obfs_password'] = p['obfs-password']
    return _node(name, 'hysteria2', server, port, config)


def _parse_tuic(name, server, port, p):
    config = {
        'uuid': p.get('uuid', ''),
        'password': p.get('password', ''),
        'sni': p.get('sni', p.get('servername', '')),
        'allowInsecure': p.get('skip-cert-verify', False),
        'congestion_control': p.get('congestion-controller',
                                    p.get('congestion_control', 'cubic')),
        'udp_relay_mode': p.get('udp-relay-mode',
                                p.get('udp_relay_mode', 'native')),
    }
    alpn = p.get('alpn')
    if alpn:
        config['alpn'] = ','.join(alpn) if isinstance(alpn, list) else alpn
    return _node(name, 'tuic', server, port, config)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _apply_transport(config, p, network):
    """Extract ws-opts / h2-opts / grpc-opts from a Clash proxy dict."""
    if network == 'ws':
        ws = p.get('ws-opts', {}) or {}
        if ws.get('path'):
            config['ws_path'] = ws['path']
        headers = ws.get('headers')
        if isinstance(headers, dict) and headers.get('Host'):
            config['ws_host'] = headers['Host']
    elif network in ('h2', 'http'):
        h2 = p.get('h2-opts', {}) or {}
        if h2.get('path'):
            config['h2_path'] = h2['path']
        if h2.get('host'):
            host = h2['host']
            config['h2_host'] = host[0] if isinstance(host, list) else host
    elif network == 'grpc':
        grpc = p.get('grpc-opts', {}) or {}
        if grpc.get('grpc-service-name'):
            config['grpc_service_name'] = grpc['grpc-service-name']


def _to_int(v):
    """Best-effort int conversion (accepts '100' / 100 / '100 Mbps')."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _node(name, protocol, address, port, config):
    return {
        'name': name,
        'protocol': protocol,
        'address': address,
        'port': port,
        'config_json': json.dumps(config),
    }
