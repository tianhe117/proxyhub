"""hysteria2 URI parser.

Accepts ``hy2://`` and ``hysteria2://`` prefixes.
hy2://password@host:port?params#name — params include sni, alpn, insecure,
up/down (mbps), obfs, obfs-password.
"""

import json
import urllib.parse

from .base import parse_kv_params


def parse_uri(uri):
    """Parse a hysteria2 URI into a node dict, or None on failure."""
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
            'sni': params.get('sni', params.get('peer', '')),
            'allowInsecure': params.get('insecure') in ('1', 'true'),
        }
        if params.get('alpn'):
            config['alpn'] = params['alpn']
        if params.get('up'):
            try:
                config['up_mbps'] = int(params['up'])
            except ValueError:
                pass
        if params.get('down'):
            try:
                config['down_mbps'] = int(params['down'])
            except ValueError:
                pass
        if params.get('obfs'):
            config['obfs'] = params['obfs']
            if params.get('obfs-password'):
                config['obfs_password'] = params['obfs-password']

        return {
            'name': name,
            'protocol': 'hysteria2',
            'address': host,
            'port': port,
            'config_json': json.dumps(config),
        }
    except Exception:
        return None
