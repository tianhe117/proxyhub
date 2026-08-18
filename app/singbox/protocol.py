"""Protocol mapping layer — DB rows → sing-box inbound/outbound dicts.

Pure functions, zero dependencies (no IO, no db import). Each protocol
maps to exactly one sing-box dict. Adding a new protocol means adding
one elif branch here + the protocol string in settings.py.
"""

import json

from app.settings import VALID_INBOUND_PROTOCOLS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Outbound protocol builders
# ---------------------------------------------------------------------------

def _build_vmess(tag, address, port, cfg):
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


def _build_vless(tag, address, port, cfg):
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


def _build_trojan(tag, address, port, cfg):
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


def _build_ss(tag, address, port, cfg):
    return {
        'type': 'shadowsocks',
        'tag': tag,
        'server': address,
        'server_port': port,
        'method': cfg.get('method', 'aes-256-gcm'),
        'password': cfg.get('password', ''),
    }


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


_OUTBOUND_BUILDERS = {
    'vmess':     _build_vmess,
    'vless':     _build_vless,
    'trojan':    _build_trojan,
    'ss':        _build_ss,
    'hysteria2': _build_hysteria2,
    'tuic':      _build_tuic,
}


# ---------------------------------------------------------------------------
# Inbound protocol builders
# ---------------------------------------------------------------------------

def _build_http_inbound(tag, listen, port, params):
    ib = {'type': 'http', 'tag': tag, 'listen': listen, 'listen_port': port}
    user, pwd = params.get('username', ''), params.get('password', '')
    if user or pwd:
        ib['users'] = [{'username': user, 'password': pwd}]
    return ib


def _build_socks_inbound(tag, listen, port, params):
    ib = {'type': 'socks', 'tag': tag, 'listen': listen, 'listen_port': port}
    user, pwd = params.get('username', ''), params.get('password', '')
    if user or pwd:
        ib['users'] = [{'username': user, 'password': pwd}]
    return ib


def _build_ss_inbound(tag, listen, port, params):
    return {
        'type': 'shadowsocks',
        'tag': tag,
        'listen': listen,
        'listen_port': port,
        'method': params.get('method', 'aes-256-gcm'),
        'password': params.get('password', ''),
    }


def _build_vmess_inbound(tag, listen, port, params):
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


_INBOUND_BUILDERS = {
    'http':   _build_http_inbound,
    'socks':  _build_socks_inbound,
    'ss':     _build_ss_inbound,
    'vmess':  _build_vmess_inbound,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_outbound(tag, address, port, protocol, config_json):
    """Build a single real-node outbound dict from protocol info.

    Args:
        tag:        sing-box outbound tag (e.g. 'n12')
        address:    server address
        port:       server port
        protocol:   protocol string (vmess/vless/trojan/ss/hysteria2/tuic/direct)
        config_json: protocol-specific config (str or dict)

    Returns:
        dict: sing-box outbound config

    Raises:
        ValueError: if protocol is not supported
    """
    if protocol == 'direct':
        return {'type': 'direct', 'tag': tag}

    cfg = _parse_json(config_json)
    builder = _OUTBOUND_BUILDERS.get(protocol)
    if builder is None:
        raise ValueError(f'sing-box does not support outbound protocol: {protocol}')
    return builder(tag, address, int(port), cfg)


def build_inbound(tag, protocol, listen, port, params_json):
    """Build a single user inbound dict from protocol info.

    Args:
        tag:        sing-box inbound tag (e.g. 'i8')
        protocol:   protocol string (http/socks/ss/vmess)
        listen:     listen address (default '0.0.0.0')
        port:       listen port
        params_json: protocol-specific params (str or dict)

    Returns:
        dict: sing-box inbound config

    Raises:
        ValueError: if protocol is not supported
    """
    if protocol not in VALID_INBOUND_PROTOCOLS:
        raise ValueError(f'Unsupported inbound protocol: {protocol}')

    params = _parse_json(params_json)
    listen = listen or '0.0.0.0'
    builder = _INBOUND_BUILDERS[protocol]
    return builder(tag, listen, int(port), params)
