"""Subscription refresh orchestration: fetch, decode, parse, and sync."""

import base64
import ssl
import urllib.request
from datetime import datetime

from app.db import subscription as db_sub
from app.parser import parse_all
from app.utils import log


def refresh_subscription(sub_id):
    """Full refresh flow: fetch → decode → parse → diff-sync → metadata."""
    sub = db_sub.get_by_id(sub_id)
    if not sub:
        return {'success': False, 'message': 'Subscription not found'}

    name = sub['name']
    url = sub['url']
    include = sub['filter_keywords'] or ''
    exclude = sub['exclude_keywords'] or ''

    log.info(f'Refreshing subscription "{name}" ...')
    try:
        body, info = fetch_subscription(url)
    except Exception as e:
        log.error(f'Fetch failed for "{name}": {e}')
        return {'success': False, 'message': f'Fetch failed: {e}'}

    text = decode_body(body)
    nodes = parse_all(text, include, exclude)

    if nodes:
        result = db_sub.apply_node_diff(sub_id, nodes)
        added = result['inserted']
        updated = result['updated']
        removed = result['deleted']
        log.info(f'"{name}" synced: +{added} ~{updated} -{removed} '
                 f'(total {len(nodes)})')
    else:
        db_sub.clear_nodes(sub_id)
        added = updated = 0
        removed = 0
        log.info(f'"{name}" parsed 0 nodes; cleared stale entries')

    db_sub.update(
        sub_id,
        updated_at=datetime.now().isoformat(),
        upload_bytes=info.get('upload', 0),
        download_bytes=info.get('download', 0),
        total_bytes=info.get('total', 0),
        expire_at=info.get('expire', 0),
    )

    return {
        'success': True,
        'message': f'{len(nodes)} nodes synced',
        'total': len(nodes),
        'added': added,
        'updated': updated,
        'removed': removed,
    }


def fetch_subscription(url):
    """Fetch subscription content with Clash-friendly headers."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'ClashForAndroid/2.5.12')
    req.add_header('Accept', '*/*')

    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        body = resp.read()
        userinfo = resp.headers.get('Subscription-Userinfo', '')
        return body, parse_userinfo(userinfo)


def parse_userinfo(header_value):
    """Parse a Subscription-Userinfo header into integer fields."""
    info = {}
    if not header_value:
        return info
    for part in header_value.split(';'):
        part = part.strip()
        if '=' in part:
            key, value = part.split('=', 1)
            try:
                info[key.strip()] = int(value.strip())
            except ValueError:
                pass
    return info


def decode_body(body):
    """Base64-unwrap URI subscriptions, otherwise return the source text."""
    try:
        text = body.decode('utf-8', errors='replace')
    except Exception:
        return ''
    try:
        padded = text
        missing = len(padded) % 4
        if missing:
            padded += '=' * (4 - missing)
        try:
            decoded = base64.urlsafe_b64decode(padded).decode('utf-8', errors='replace')
        except Exception:
            decoded = base64.b64decode(padded).decode('utf-8', errors='replace')
        if 'vmess://' in decoded or 'ss://' in decoded or 'vless://' in decoded:
            return decoded
    except Exception:
        pass
    return text
