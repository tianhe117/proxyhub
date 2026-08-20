"""vmess:// URI parser.

vmess://<base64(json)>. Legacy field names (add/port/id/aid/net/ps/host/path/tls)
are mapped to the v2 config_json keys consumed by singbox/protocol.py.
"""

import base64
import json


def parse_uri(uri):
    """Parse a ``vmess://`` URI into a node dict, or None on failure."""
    try:
        b64 = uri[len('vmess://'):]
        b64 += '=' * (-len(b64) % 4)
        try:
            decoded = base64.urlsafe_b64decode(b64).decode('utf-8')
        except Exception:
            decoded = base64.b64decode(b64).decode('utf-8')
        data = json.loads(decoded)

        name = data.get('ps') or 'Unnamed'
        address = data.get('add', '')
        port = int(data.get('port', 0))
        net = data.get('net', 'tcp')
        tls = data.get('tls', '')
        security = data.get('type', 'none')
        if security == 'none':
            security = 'auto'

        config = {
            'uuid': data.get('id', ''),
            'alterId': int(data.get('aid', 0)),
            'security': security,
            'network': net,
            'tls': tls in ('tls', '1', 'true', True),
            'allowInsecure': tls == 'allowInsecure',
        }
        if net == 'ws':
            if data.get('host'):
                config['ws_host'] = data['host']
            if data.get('path'):
                config['ws_path'] = data['path']
        elif net in ('h2', 'http'):
            if data.get('host'):
                config['h2_host'] = data['host']
            if data.get('path'):
                config['h2_path'] = data['path']
        elif net == 'grpc':
            if data.get('path'):
                config['grpc_service_name'] = data['path']

        return {
            'name': name,
            'protocol': 'vmess',
            'address': address,
            'port': port,
            'config_json': json.dumps(config),
        }
    except Exception:
        return None
