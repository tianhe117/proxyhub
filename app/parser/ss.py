"""ss:// URI parser.

Supports SIP002 (``ss://base64(method:password)@host:port#name`` with optional
``?plugin=...``) and the legacy full-base64 form
(``ss://base64(method:password@host:port)``).
"""

import base64
import json
import re
import urllib.parse


def parse_uri(uri):
    """Parse an ``ss://`` URI into a node dict, or None on failure."""
    try:
        body = uri[len('ss://'):]

        # Fragment (node name)
        name = 'Unnamed'
        if '#' in body:
            body, fragment = body.split('#', 1)
            name = urllib.parse.unquote(fragment)

        # Query params (plugin)
        plugin = ''
        plugin_opts = ''
        if '?' in body:
            body, query = body.split('?', 1)
            params = urllib.parse.parse_qs(query)
            raw_plugin = params.get('plugin', [''])[0]
            if raw_plugin:
                raw_plugin = urllib.parse.unquote(raw_plugin)
                if ';' in raw_plugin:
                    parts = raw_plugin.split(';', 1)
                    plugin = parts[0]
                    plugin_opts = parts[1] if len(parts) > 1 else ''
                else:
                    plugin = raw_plugin

        if '@' in body:
            # SIP002: userinfo@server:port
            userinfo_b64, server_part = body.split('@', 1)
            userinfo_b64 += '=' * (-len(userinfo_b64) % 4)
            try:
                userinfo = base64.urlsafe_b64decode(userinfo_b64).decode('utf-8')
            except Exception:
                userinfo = base64.b64decode(userinfo_b64).decode('utf-8')
            method, password = userinfo.split(':', 1)
            server_part = server_part.rstrip('/')
            if ':' in server_part:
                address, port_str = server_part.rsplit(':', 1)
                port = int(port_str)
            else:
                address = server_part
                port = 8388
        else:
            # Legacy: ss://base64(method:password@server:port)
            padded = body + '=' * (-len(body) % 4)
            try:
                decoded = base64.urlsafe_b64decode(padded).decode('utf-8')
            except Exception:
                decoded = base64.b64decode(padded).decode('utf-8')
            match = re.match(r'^([^:]+):([^@]+)@(.+):(\d+)$', decoded)
            if not match:
                return None
            method, password, address, port_str = match.groups()
            port = int(port_str)

        config = {'method': method, 'password': password}
        if plugin and 'obfs' in plugin:
            config['plugin'] = 'obfs-local'
            if plugin_opts:
                config['plugin_opts'] = plugin_opts

        return {
            'name': name,
            'protocol': 'ss',
            'address': address,
            'port': port,
            'config_json': json.dumps(config),
        }
    except Exception:
        return None
