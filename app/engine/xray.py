"""Xray JSON configuration generation (§14.1)."""

import json


# ---------------------------------------------------------------------------
# Outbound config (SOCKS5 in → protocol out to remote)
# ---------------------------------------------------------------------------

def build_xray_outbound(node, local_port):
    """Build a complete Xray config with SOCKS5 inbound + remote outbound.

    Args:
        node: dict/row with protocol, address, port, config_json
        local_port: int — SOCKS5 listen port

    Returns:
        JSON-serialisable dict
    """
    cfg = _get_config(node)
    protocol = node['protocol'] 
    address = node['address'] 
    port = int(node['port'])

    outbound = _build_outbound(protocol, address, port, cfg)
    stream = build_stream_settings(cfg)
    if stream:
        outbound['streamSettings'] = stream

    return {
        'inbounds': [{
            'protocol': 'socks',
            'port': local_port,
            'listen': '127.0.0.1',
        }],
        'outbounds': [outbound],
    }


def _get_config(node):
    """Normalise node config_json to a dict."""
    cfg = node['config_json'] 
    if isinstance(cfg, str):
        return json.loads(cfg)
    return cfg or {}


def _build_outbound(protocol, address, port, cfg):
    """Build the outbound dict for the given protocol."""
    if protocol == 'vmess':
        return {
            'protocol': 'vmess',
            'settings': {
                'vnext': [{
                    'address': address,
                    'port': port,
                    'users': [{
                        'id': cfg.get('uuid') or cfg.get('id', ''),
                        'alterId': int(cfg.get('alterId', 0)),
                        'security': cfg.get('security', 'auto'),
                    }],
                }],
            },
        }
    elif protocol == 'vless':
        user = {
            'id': cfg.get('uuid') or cfg.get('id', ''),
            'encryption': cfg.get('encryption', 'none'),
        }
        if cfg.get('flow'):
            user['flow'] = cfg['flow']
        return {
            'protocol': 'vless',
            'settings': {
                'vnext': [{
                    'address': address,
                    'port': port,
                    'users': [user],
                }],
            },
        }
    elif protocol == 'trojan':
        return {
            'protocol': 'trojan',
            'settings': {
                'servers': [{
                    'address': address,
                    'port': port,
                    'password': cfg.get('password', ''),
                }],
            },
        }
    elif protocol in ('ss', 'ssr'):
        return {
            'protocol': 'shadowsocks',
            'settings': {
                'servers': [{
                    'address': address,
                    'port': port,
                    'method': cfg.get('method', 'aes-256-gcm'),
                    'password': cfg.get('password', ''),
                }],
            },
        }
    else:
        raise ValueError(f'Xray does not support protocol: {protocol}')


# ---------------------------------------------------------------------------
# Stream settings
# ---------------------------------------------------------------------------

def build_stream_settings(cfg):
    """Build Xray streamSettings dict from node config_json fields.

    Uses snake_case keys from cfg (ws_host, grpc_service_name, etc.)
    Outputs camelCase keys as expected by Xray.
    """
    network = cfg.get('network', 'tcp')
    stream = {
        'network': network,
        'security': 'tls' if cfg.get('tls') else 'none',
    }

    # TLS
    if cfg.get('tls'):
        tls = {}
        if cfg.get('sni'):
            tls['serverName'] = cfg['sni']
        if cfg.get('allowInsecure'):
            tls['allowInsecure'] = True
        if cfg.get('fingerprint'):
            tls['fingerprint'] = cfg['fingerprint']
        if cfg.get('alpn'):
            alpn = cfg['alpn']
            tls['alpn'] = alpn.split(',') if isinstance(alpn, str) else alpn
        if tls:
            stream['tlsSettings'] = tls

    # Transport
    if network == 'ws':
        ws = {}
        if cfg.get('ws_host'):
            ws['headers'] = {'Host': cfg['ws_host']}
        if cfg.get('ws_path'):
            ws['path'] = cfg['ws_path']
        if ws:
            stream['wsSettings'] = ws
    elif network in ('h2', 'http'):
        h2 = {}
        if cfg.get('h2_host'):
            host = cfg['h2_host']
            h2['host'] = [host] if isinstance(host, str) else host
        if cfg.get('h2_path'):
            h2['path'] = cfg['h2_path']
        if h2:
            stream['httpSettings'] = h2
    elif network == 'grpc':
        grpc = {}
        if cfg.get('grpc_service_name'):
            grpc['serviceName'] = cfg['grpc_service_name']
        if grpc:
            stream['grpcSettings'] = grpc

    return stream


# ---------------------------------------------------------------------------
# Inbound config (user-facing listener → SOCKS5)
# ---------------------------------------------------------------------------

def build_xray_inbound(inbound, socks_port):
    """Build Xray config that listens on the user port and forwards to SOCKS5.

    Args:
        inbound: dict/row with protocol, port, listen_addr, params_json
        socks_port: int — local SOCKS5 port to forward to

    Returns:
        JSON-serialisable dict
    """
    protocol = inbound['protocol']
    port = int(inbound['port'])
    listen = '0.0.0.0'
    try:
        listen = inbound['listen_addr']
    except (KeyError, AttributeError):
        pass

    params = inbound['params_json']
    if isinstance(params, str):
        params = json.loads(params)
    elif params is None:
        params = {}

    # Build the inbound listener
    if protocol == 'http':
        inbound_config = {'protocol': 'http', 'port': port, 'listen': listen}
        user = params.get('username', '')
        pwd = params.get('password', '')
        if user or pwd:
            inbound_config['settings'] = {
                'accounts': [{'user': user, 'pass': pwd}],
            }
    elif protocol == 'socks':
        inbound_config = {'protocol': 'socks', 'port': port, 'listen': listen}
        user = params.get('username', '')
        pwd = params.get('password', '')
        if user or pwd:
            inbound_config['settings'] = {
                'accounts': [{'user': user, 'pass': pwd}],
            }
    elif protocol == 'ss':
        inbound_config = {
            'protocol': 'shadowsocks',  # Xray uses 'shadowsocks' not 'ss'
            'port': port,
            'listen': listen,
            'settings': {
                'method': params.get('method', 'aes-256-gcm'),
                'password': params.get('password', ''),
            },
        }
    elif protocol == 'vmess':
        inbound_config = {
            'protocol': 'vmess',
            'port': port,
            'listen': listen,
            'settings': {
                'clients': [{
                    'id': params.get('uuid', ''),
                    'alterId': int(params.get('alterId', 0)),
                }],
            },
        }
        # Stream settings for VMess inbound (ws etc.)
        net = params.get('network')
        if net:
            stream = {'network': net}
            if net == 'ws' and params.get('ws_path'):
                stream['wsSettings'] = {'path': params['ws_path']}
            if net == 'h2' and params.get('h2_path'):
                stream['httpSettings'] = {'path': params['h2_path']}
            if net == 'grpc' and params.get('grpc_service_name'):
                stream['grpcSettings'] = {'serviceName': params['grpc_service_name']}
            inbound_config['streamSettings'] = stream
    else:
        raise ValueError(f'Unsupported inbound protocol: {protocol}')

    return {
        'inbounds': [inbound_config],
        'outbounds': [{
            'protocol': 'socks',
            'settings': {
                'servers': [{
                    'address': '127.0.0.1',
                    'port': socks_port,
                }],
            },
        }],
    }
