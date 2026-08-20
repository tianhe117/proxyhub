"""tuic URI parser.

tuic://uuid:password@host:port?params#name — params include sni, alpn,
insecure, congestion_control, udp_relay_mode.
"""

import json
import urllib.parse

from .base import parse_kv_params


def parse_uri(uri):
    """Parse a ``tuic://`` URI into a node dict, or None on failure."""
    try:
        parsed = urllib.parse.urlsplit(uri)
        if '@' not in (parsed.netloc or ''):
            return None
        uuid = urllib.parse.unquote(parsed.username or '')
        password = urllib.parse.unquote(parsed.password or '')
        host = parsed.hostname
        port = int(parsed.port or 0)
        name = urllib.parse.unquote(parsed.fragment) or 'Unnamed'
        params = parse_kv_params(parsed.query)

        config = {
            'uuid': uuid,
            'password': password,
            'sni': params.get('sni', params.get('peer', '')),
            'allowInsecure': params.get('insecure') in ('1', 'true'),
            'congestion_control': params.get('congestion_control',
                                             params.get('congestion-controller', 'cubic')),
            'udp_relay_mode': params.get('udp_relay_mode',
                                         params.get('udp-relay-mode', 'native')),
        }
        if params.get('alpn'):
            config['alpn'] = params['alpn']

        return {
            'name': name,
            'protocol': 'tuic',
            'address': host,
            'port': port,
            'config_json': json.dumps(config),
        }
    except Exception:
        return None
