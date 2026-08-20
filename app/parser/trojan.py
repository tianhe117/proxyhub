"""trojan:// URI parser.

trojan://password@host:port?params#name — params include sni, alpn, type
(network), allowInsecure, etc.
"""

import json
import urllib.parse

from .base import parse_kv_params


def parse_uri(uri):
    """Parse a ``trojan://`` URI into a node dict, or None on failure."""
    try:
        parsed = urllib.parse.urlsplit(uri)
        if '@' not in (parsed.netloc or ''):
            return None
        password = urllib.parse.unquote(parsed.username or '')
        host = parsed.hostname
        port = int(parsed.port or 0)
        name = urllib.parse.unquote(parsed.fragment) or 'Unnamed'
        params = parse_kv_params(parsed.query)

        config = {
            'password': password,
            'network': params.get('type', 'tcp'),
            'sni': params.get('sni', params.get('servername', '')),
            'allowInsecure': params.get('allowInsecure') in ('1', 'true'),
            'fingerprint': params.get('fp', params.get('fingerprint', '')),
            'tls': True,
        }
        if params.get('alpn'):
            config['alpn'] = params['alpn']
        if config['network'] == 'ws':
            if params.get('host'):
                config['ws_host'] = params['host']
            if params.get('path'):
                config['ws_path'] = params['path']
        elif config['network'] in ('h2', 'http'):
            if params.get('host'):
                config['h2_host'] = params['host']
            if params.get('path'):
                config['h2_path'] = params['path']
        elif config['network'] == 'grpc':
            if params.get('serviceName'):
                config['grpc_service_name'] = params['serviceName']

        return {
            'name': name,
            'protocol': 'trojan',
            'address': host,
            'port': port,
            'config_json': json.dumps(config),
        }
    except Exception:
        return None
