"""sing-box JSON configuration generation (§14.3).

Key differences from Xray:
- Uses 'type' instead of 'protocol'
- 'listen_port' instead of 'port' (inbound)
- 'server_port' instead of 'port' (outbound)
- 'tls.server_name' instead of 'tlsSettings.serverName'
- 'tls.insecure' instead of 'tlsSettings.allowInsecure'
"""

import json


def generate_singbox_config(node, local_port):
    """Generate sing-box config JSON.

    Args:
        node: dict/row with protocol, address, port, config_json
        local_port: int — local SOCKS5 listen port

    Returns:
        JSON-serialisable dict
    """
    protocol = node['protocol'] 
    # Protocol aliases: hysteria2 / hy2 / hysteria all map to hysteria2
    if protocol in ('hysteria2', 'hy2', 'hysteria'):
        sing_type = 'hysteria2'
    elif protocol == 'tuic':
        sing_type = 'tuic'
    else:
        raise ValueError(f'sing-box does not support protocol: {protocol}')

    address = node['address'] 
    port = int(node['port'])

    cfg = node['config_json'] 
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    elif cfg is None:
        cfg = {}

    outbound = _build_outbound(sing_type, address, port, cfg)

    return {
        'inbounds': [{
            'type': 'socks',
            'listen': '127.0.0.1',
            'listen_port': local_port,
        }],
        'outbounds': [outbound],
    }


def _build_outbound(sing_type, address, port, cfg):
    """Build the outbound dict for sing-box."""
    if sing_type == 'hysteria2':
        ob = {
            'type': 'hysteria2',
            'server': address,
            'server_port': port,
            'password': cfg.get('password', ''),
            'tls': {
                'enabled': True,
                'server_name': cfg.get('sni', ''),
            },
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
        # obfs (salamander)
        if cfg.get('obfs'):
            ob['obfs'] = {
                'type': 'salamander',
                'password': cfg.get('obfs_password', ''),
            }
        return ob

    elif sing_type == 'tuic':
        ob = {
            'type': 'tuic',
            'server': address,
            'server_port': port,
            'uuid': cfg.get('uuid', ''),
            'password': cfg.get('password', ''),
            'tls': {
                'enabled': True,
                'server_name': cfg.get('sni', ''),
            },
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

    raise ValueError(f'Unknown sing-box type: {sing_type}')
