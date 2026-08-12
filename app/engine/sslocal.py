"""sslocal JSON configuration generation (§14.2).

Produces the flat JSON format expected by shadowsocks-rust's sslocal binary.
"""


def generate_sslocal_config(node, local_port, cfg):
    """Generate sslocal config JSON.

    Args:
        node: dict with address, port, protocol
        local_port: int — local SOCKS5 listen port
        cfg:   parsed config_json dict

    Returns:
        JSON-serialisable dict

    Raises:
        ValueError: node.protocol is not 'ss'
    """
    protocol = node['protocol']
    if protocol != 'ss':
        raise ValueError(f'sslocal only supports ss protocol, got: {protocol}')

    address = node['address']
    port = int(node['port'])

    config = {
        'server':        address,
        'server_port':   port,
        'password':      cfg.get('password', ''),
        'method':        cfg.get('method', 'aes-256-gcm'),
        'local_address': '127.0.0.1',
        'local_port':    local_port,
    }

    # Plugin support — only obfs-local
    plugin = cfg.get('plugin', '')
    if plugin and 'obfs' in plugin:
        config['plugin'] = 'obfs-local'
        if cfg.get('plugin_opts'):
            config['plugin_opts'] = cfg['plugin_opts']

    return config
