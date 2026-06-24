"""Subscription fetching, parsing, and node import (§5.2, §7)."""

import json
import base64
import re
import ssl
import urllib.request
import urllib.parse
from datetime import datetime

import yaml

from app.models.subscription import get_by_id, update, clear_nodes, batch_insert_nodes
from app.logger import log


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def refresh_subscription(sub_id):
    """Full refresh flow: fetch → parse → filter → store nodes.

    Returns:
        dict: {success, message, node_count}
    """
    sub = get_by_id(sub_id)
    if not sub:
        return {'success': False, 'message': 'Subscription not found'}

    url = sub['url']
    filter_kw = sub['filter_keywords'] or ''
    exclude_kw = sub['exclude_keywords'] or ''

    log('info', 'subscription', f'Refreshing {sub["name"]} ...')

    # 1. Fetch
    try:
        body, info = _fetch_subscription(url)
    except Exception as e:
        log('error', 'subscription', f'Fetch failed for {sub["name"]}: {e}')
        return {'success': False, 'message': f'Fetch failed: {e}'}

    # 2. Decode
    content = _decode_body(body)

    # 3. Parse
    nodes = _parse_content(content)

    # 4. Filter
    nodes = _apply_filters(nodes, filter_kw, exclude_kw)

    # 5. Store
    clear_nodes(sub_id)
    if nodes:
        batch_insert_nodes(sub_id, nodes)

    # 6. Update subscription metadata
    update(sub_id, updated_at=datetime.now().isoformat(),
           upload_bytes=info.get('upload', 0),
           download_bytes=info.get('download', 0),
           total_bytes=info.get('total', 0),
           expire_at=info.get('expire', 0))

    log('ok', 'subscription', f'{sub["name"]}: {len(nodes)} nodes imported')
    return {'success': True, 'message': f'{len(nodes)} nodes imported',
            'node_count': len(nodes)}


# ---------------------------------------------------------------------------
# HTTP fetching
# ---------------------------------------------------------------------------

def _fetch_subscription(url):
    """Fetch subscription content with Clash-friendly headers.

    Returns: (body_bytes, user_info_dict)
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'ClashForAndroid/2.5.12')
    req.add_header('Accept', '*/*')

    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        body = resp.read()

        # Parse Subscription-Userinfo header
        info = {}
        userinfo = resp.headers.get('Subscription-Userinfo', '')
        if userinfo:
            for part in userinfo.split(';'):
                part = part.strip()
                if '=' in part:
                    k, v = part.split('=', 1)
                    try:
                        info[k.strip()] = int(v.strip())
                    except ValueError:
                        pass

        return body, info


def _decode_body(body):
    """Try Base64 decoding; return decoded text if it contains proxy URIs."""
    try:
        # Pad to multiple of 4
        padded = body.decode('ascii')
        missing = len(padded) % 4
        if missing:
            padded += '=' * (4 - missing)
        decoded = base64.b64decode(padded).decode('utf-8', errors='replace')
        if 'vmess://' in decoded or 'ss://' in decoded:
            return decoded
    except Exception:
        pass

    return body.decode('utf-8', errors='replace')


# ---------------------------------------------------------------------------
# Format detection + dispatch
# ---------------------------------------------------------------------------

def _parse_content(content):
    """Detect format and parse into node dicts."""
    stripped = content.strip()

    # Clash YAML detection
    if stripped.startswith('mixed-port:') or 'proxies:' in stripped:
        return _parse_clash_yaml(stripped)

    # Standard format — line-by-line
    return _parse_standard(stripped)


def _parse_standard(content):
    """Parse standard (line-by-line vmess:// / ss://) format."""
    nodes = []
    for line in content.splitlines():
        line = line.strip()
        if line.startswith('vmess://'):
            node = _parse_vmess_link(line)
            if node:
                nodes.append(node)
        elif line.startswith('ss://'):
            node = _parse_ss_link(line)
            if node:
                nodes.append(node)
    return nodes


# ---------------------------------------------------------------------------
# vmess:// parser (§7.3)
# ---------------------------------------------------------------------------

def _parse_vmess_link(line):
    """Parse vmess://<base64_json> into a node dict."""
    try:
        b64 = line[len('vmess://'):]
        missing = len(b64) % 4
        if missing:
            b64 += '=' * (4 - missing)
        decoded = base64.b64decode(b64).decode('utf-8')
        data = json.loads(decoded)

        name = data.get('ps', 'Unnamed')
        address = data.get('add', '')
        port = int(data.get('port', 0))
        config = {
            'id':       data.get('id', ''),
            'aid':      int(data.get('aid', 0)),
            'net':      data.get('net', 'tcp'),
            'type':     data.get('type', 'none'),
            'host':     data.get('host', ''),
            'path':     data.get('path', ''),
            'tls':      data.get('tls', ''),
        }

        return {
            'name':        name,
            'protocol':    'vmess',
            'address':     address,
            'port':        port,
            'config_json': json.dumps(_vmess_config_to_standard(config)),
            'bin_type':    'xray',
        }
    except Exception:
        return None


def _vmess_config_to_standard(cfg):
    """Convert legacy vmess config keys to our standard snake_case keys."""
    net = cfg.get('net', 'tcp')
    tls = cfg.get('tls', '')
    result = {
        'uuid':         cfg.get('id', ''),
        'alterId':      cfg.get('aid', 0),
        'security':     cfg.get('type', 'auto') if cfg.get('type') != 'none' else 'auto',
        'network':      net,
        'tls':          tls in ('tls', '1', 'true', True),
        'allowInsecure': True if tls == 'allowInsecure' else False,
    }
    if net == 'ws':
        if cfg.get('host'):
            result['ws_host'] = cfg['host']
        if cfg.get('path'):
            result['ws_path'] = cfg['path']
    elif net == 'h2':
        if cfg.get('host'):
            result['h2_host'] = cfg['host']
        if cfg.get('path'):
            result['h2_path'] = cfg['path']
    elif net == 'grpc':
        if cfg.get('path'):
            result['grpc_service_name'] = cfg['path']
    return result


# ---------------------------------------------------------------------------
# ss:// parser (§7.4)
# ---------------------------------------------------------------------------

def _parse_ss_link(line):
    """Parse ss:// links (SIP002 and legacy formats)."""
    try:
        uri = line[len('ss://'):]

        # Fragment (name)
        name = 'Unnamed'
        if '#' in uri:
            uri, fragment = uri.split('#', 1)
            name = urllib.parse.unquote(fragment)

        # Query params (plugin)
        plugin = ''
        plugin_opts = ''
        if '?' in uri:
            uri, query = uri.split('?', 1)
            params = urllib.parse.parse_qs(query)
            plugin = params.get('plugin', [''])[0]
            if plugin:
                plugin_full = urllib.parse.unquote(plugin)
                if ';' in plugin_full:
                    parts = plugin_full.split(';', 1)
                    plugin = parts[0]
                    plugin_opts = parts[1] if len(parts) > 1 else ''

        # Split userinfo@server:port
        if '@' in uri:
            userinfo_b64, server_part = uri.split('@', 1)
            # Decode userinfo
            missing = len(userinfo_b64) % 4
            if missing:
                userinfo_b64 += '=' * (4 - missing)
            try:
                userinfo = base64.b64decode(userinfo_b64).decode('utf-8')
                method, password = userinfo.split(':', 1)
            except Exception:
                return None

            # Server:port
            server_part = server_part.rstrip('/')
            if ':' in server_part:
                address, port_str = server_part.rsplit(':', 1)
                port = int(port_str)
            else:
                address = server_part
                port = 8388
        else:
            # Legacy format — entire string is base64(method:password@server:port)
            missing = len(uri) % 4
            if missing:
                uri += '=' * (4 - missing)
            try:
                decoded = base64.b64decode(uri).decode('utf-8')
            except Exception:
                return None
            # method:password@server:port
            match = re.match(r'^([^:]+):([^@]+)@(.+):(\d+)$', decoded)
            if not match:
                return None
            method, password, address, port = match.groups()
            port = int(port)

        # Determine bin_type
        bin_type = 'sslocal' if plugin and 'obfs' in plugin else 'xray'

        config = {
            'method':   method,
            'password': password,
        }
        if plugin and 'obfs' in plugin:
            config['plugin'] = 'obfs-local'
            if plugin_opts:
                config['plugin_opts'] = plugin_opts

        return {
            'name':        name,
            'protocol':    'ss',
            'address':     address,
            'port':        port,
            'config_json': json.dumps(config),
            'bin_type':    bin_type,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Clash YAML parser (§7.5)
# ---------------------------------------------------------------------------

def _parse_clash_yaml(content):
    """Parse Clash YAML subscription format."""
    try:
        data = yaml.safe_load(content)
        proxies = data.get('proxies', [])
    except yaml.YAMLError:
        # Try extracting just the proxies block
        proxies = _extract_proxies_block(content)

    nodes = []
    for p in proxies or []:
        if not isinstance(p, dict):
            continue
        node = _parse_clash_proxy(p)
        if node:
            nodes.append(node)
    return nodes


def _extract_proxies_block(content):
    """Extract the proxies: block when the full YAML is malformed."""
    lines = content.splitlines()
    in_proxies = False
    proxy_lines = []
    for line in lines:
        if not in_proxies:
            if line.strip().startswith('proxies:'):
                in_proxies = True
                continue
        else:
            # Stop at next top-level key (non-indented, non-list)
            if line and not line[0].isspace() and not line.strip().startswith('-'):
                if ':' in line and not line.startswith(' '):
                    break
            proxy_lines.append(line)
    try:
        return yaml.safe_load('\n'.join(proxy_lines))
    except Exception:
        return []


def _parse_clash_proxy(p):
    """Parse a single Clash proxy dict into our node format."""
    ptype = p.get('type', '').lower()
    name = p.get('name', 'Unnamed')
    server = p.get('server', '')
    port = int(p.get('port', 0))

    if ptype == 'ss':
        return _parse_clash_ss(name, server, port, p)
    elif ptype == 'ssr':
        return _parse_clash_ssr(name, server, port, p)
    elif ptype == 'vmess':
        return _parse_clash_vmess(name, server, port, p)
    elif ptype == 'vless':
        return _parse_clash_vless(name, server, port, p)
    elif ptype == 'trojan':
        return _parse_clash_trojan(name, server, port, p)
    elif ptype in ('hysteria', 'hysteria2', 'hy2'):
        return _parse_clash_hysteria(name, server, port, p)
    elif ptype == 'tuic':
        return _parse_clash_tuic(name, server, port, p)
    elif ptype == 'anytls':
        return _parse_clash_anytls(name, server, port, p)
    return None


def _parse_clash_ss(name, server, port, p):
    config = {
        'method':   p.get('cipher', 'aes-256-gcm'),
        'password': p.get('password', ''),
    }
    bin_type = 'xray'
    plugin = p.get('plugin', '')
    if plugin == 'obfs':
        popts = p.get('plugin-opts', {})
        config['plugin'] = 'obfs-local'
        mode = popts.get('mode', 'http')
        host = popts.get('host', '')
        config['plugin_opts'] = f'obfs={mode}'
        if host:
            config['plugin_opts'] += f';obfs-host={host}'
        bin_type = 'sslocal'
    return {
        'name': name, 'protocol': 'ss',
        'address': server, 'port': port,
        'config_json': json.dumps(config), 'bin_type': bin_type,
    }


def _parse_clash_ssr(name, server, port, p):
    config = {
        'cipher':         p.get('cipher', 'aes-256-cfb'),
        'password':       p.get('password', ''),
        'obfs':           p.get('obfs', 'plain'),
        'protocol':       p.get('protocol', 'origin'),
        'obfs_param':     p.get('obfs-param', ''),
        'protocol_param': p.get('protocol-param', ''),
    }
    return {'name': name, 'protocol': 'ssr', 'address': server, 'port': port,
            'config_json': json.dumps(config), 'bin_type': 'xray'}


def _parse_clash_vmess(name, server, port, p):
    network = p.get('network', 'tcp')
    config = {
        'uuid':          p.get('uuid', ''),
        'alterId':       int(p.get('alterId', 0)),
        'security':      p.get('cipher', 'auto'),
        'network':       network,
        'tls':           p.get('tls', False),
        'sni':           p.get('servername', p.get('sni', '')),
        'allowInsecure': p.get('skip-cert-verify', False),
        'fingerprint':   p.get('fingerprint', ''),
    }
    _apply_clash_transport(config, p, network)
    return {'name': name, 'protocol': 'vmess', 'address': server, 'port': port,
            'config_json': json.dumps(config), 'bin_type': 'xray'}


def _parse_clash_vless(name, server, port, p):
    network = p.get('network', 'tcp')
    config = {
        'uuid':          p.get('uuid', ''),
        'encryption':    p.get('encryption', 'none'),
        'flow':          p.get('flow', ''),
        'network':       network,
        'tls':           p.get('tls', False),
        'sni':           p.get('servername', p.get('sni', '')),
        'allowInsecure': p.get('skip-cert-verify', False),
        'fingerprint':   p.get('fingerprint', ''),
    }
    # reality-opts
    reality = p.get('reality-opts', {})
    if reality:
        if reality.get('public-key'):
            config['reality_public_key'] = reality['public-key']
        if reality.get('short-id'):
            config['reality_short_id'] = reality['short-id']
    _apply_clash_transport(config, p, network)
    return {'name': name, 'protocol': 'vless', 'address': server, 'port': port,
            'config_json': json.dumps(config), 'bin_type': 'xray'}


def _parse_clash_trojan(name, server, port, p):
    network = p.get('network', 'tcp')
    config = {
        'password':      p.get('password', ''),
        'sni':           p.get('sni', p.get('servername', '')),
        'alpn':          ','.join(p['alpn']) if isinstance(p.get('alpn'), list) else p.get('alpn', ''),
        'allowInsecure': p.get('skip-cert-verify', False),
        'network':       network,
        'tls':           True,
        'fingerprint':   p.get('fingerprint', ''),
    }
    _apply_clash_transport(config, p, network)
    return {'name': name, 'protocol': 'trojan', 'address': server, 'port': port,
            'config_json': json.dumps(config), 'bin_type': 'xray'}


def _parse_clash_hysteria(name, server, port, p):
    config = {
        'password':      p.get('password', p.get('auth', '')),
        'sni':           p.get('sni', p.get('servername', '')),
        'allowInsecure': p.get('skip-cert-verify', False),
    }
    if p.get('up'):
        config['up_mbps'] = p['up']
    if p.get('down'):
        config['down_mbps'] = p['down']
    if p.get('up_mbps'):
        config['up_mbps'] = p['up_mbps']
    if p.get('down_mbps'):
        config['down_mbps'] = p['down_mbps']
    # obfs (only for hy2)
    if p.get('obfs'):
        config['obfs'] = p['obfs']
    if p.get('obfs-password'):
        config['obfs_password'] = p['obfs-password']
    return {'name': name, 'protocol': 'hysteria2', 'address': server, 'port': port,
            'config_json': json.dumps(config), 'bin_type': 'sing-box'}


def _parse_clash_tuic(name, server, port, p):
    config = {
        'uuid':               p.get('uuid', ''),
        'password':           p.get('password', ''),
        'sni':                p.get('sni', p.get('servername', '')),
        'allowInsecure':      p.get('skip-cert-verify', False),
        'congestion_control': p.get('congestion-controller', p.get('congestion_control', 'cubic')),
        'udp_relay_mode':     p.get('udp-relay-mode', p.get('udp_relay_mode', 'native')),
    }
    if p.get('alpn'):
        alpn = p['alpn']
        config['alpn'] = ','.join(alpn) if isinstance(alpn, list) else alpn
    return {'name': name, 'protocol': 'tuic', 'address': server, 'port': port,
            'config_json': json.dumps(config), 'bin_type': 'sing-box'}


def _parse_clash_anytls(name, server, port, p):
    config = {
        'password':      p.get('password', ''),
        'sni':           p.get('sni', p.get('servername', '')),
        'allowInsecure': p.get('skip-cert-verify', False),
    }
    return {'name': name, 'protocol': 'anytls', 'address': server, 'port': port,
            'config_json': json.dumps(config), 'bin_type': 'xray'}


def _apply_clash_transport(config, p, network):
    """Extract transport-specific fields from a Clash proxy dict."""
    if network == 'ws':
        ws = p.get('ws-opts', {}) or {}
        if ws.get('path'):
            config['ws_path'] = ws['path']
        if ws.get('headers') and isinstance(ws['headers'], dict) and ws['headers'].get('Host'):
            config['ws_host'] = ws['headers']['Host']
    elif network in ('h2', 'http'):
        h2 = p.get('h2-opts', {}) or {}
        if h2.get('path'):
            config['h2_path'] = h2['path']
        if h2.get('host'):
            config['h2_host'] = h2['host']
    elif network == 'grpc':
        grpc = p.get('grpc-opts', {}) or {}
        if grpc.get('grpc-service-name'):
            config['grpc_service_name'] = grpc['grpc-service-name']


# ---------------------------------------------------------------------------
# Keyword filtering (§7.7)
# ---------------------------------------------------------------------------

def _apply_filters(nodes, filter_keywords, exclude_keywords):
    """Filter nodes by keyword matching (OR logic)."""
    from app.utils.helpers import split_keywords

    f_kw = split_keywords(filter_keywords)
    e_kw = split_keywords(exclude_keywords)

    if not f_kw and not e_kw:
        return nodes

    filtered = []
    for node in nodes:
        name = node.get('name', '')
        # Include: if filter keywords are set, name must contain at least one
        if f_kw:
            if not any(kw.lower() in name.lower() for kw in f_kw):
                continue
        # Exclude: if any exclude keyword matches, skip
        if e_kw:
            if any(kw.lower() in name.lower() for kw in e_kw):
                continue
        filtered.append(node)

    return filtered


# ---------------------------------------------------------------------------
# bin_type assignment (§7.6)
# ---------------------------------------------------------------------------

def assign_bin_type(protocol, plugin=''):
    """Determine bin_type from protocol and optional plugin info."""
    if protocol == 'ss' and plugin and 'obfs' in plugin:
        return 'sslocal'
    from app.settings import PROTOCOL_BIN_MAP
    return PROTOCOL_BIN_MAP.get(protocol, 'xray')
