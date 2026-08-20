"""Business service layer: subscription refresh orchestration.

Pulls a subscription URL → decodes → parses via app.parser → diff-syncs into
the DB via app.db.subscription. No sing-box coupling (no config/process calls).
"""

import base64
import ssl
import urllib.request
from datetime import datetime

from app.utils import log
from app.parser import parse_all
from app.db import subscription as db_sub


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def refresh_subscription(sub_id):
    """Full refresh flow: fetch → decode → parse → diff-sync → update metadata.

    Returns:
        dict: {success, message, total, added, updated, removed}
    """
    sub = db_sub.get_by_id(sub_id)
    if not sub:
        return {'success': False, 'message': 'Subscription not found'}

    name = sub['name']
    url = sub['url']
    include = sub['filter_keywords'] or ''
    exclude = sub['exclude_keywords'] or ''

    log.info(f'Refreshing subscription "{name}" ...')

    # 1. Fetch
    try:
        body, info = fetch_subscription(url)
    except Exception as e:
        log.error(f'Fetch failed for "{name}": {e}')
        return {'success': False, 'message': f'Fetch failed: {e}'}

    # 2. Decode (base64-wrapped URI lists → text)
    text = decode_body(body)

    # 3. Parse + filter
    nodes = parse_all(text, include, exclude)

    # 4. Diff-sync into DB (keeps node ids stable by matching name)
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

    # 5. Update subscription metadata (updated_at + traffic)
    db_sub.update(sub_id,
                  updated_at=datetime.now().isoformat(),
                  upload_bytes=info.get('upload', 0),
                  download_bytes=info.get('download', 0),
                  total_bytes=info.get('total', 0),
                  expire_at=info.get('expire', 0))

    return {
        'success': True,
        'message': f'{len(nodes)} nodes synced',
        'total': len(nodes),
        'added': added,
        'updated': updated,
        'removed': removed,
    }


# ---------------------------------------------------------------------------
# HTTP fetching + decoding
# ---------------------------------------------------------------------------

def fetch_subscription(url):
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
        userinfo = resp.headers.get('Subscription-Userinfo', '')
        info = parse_userinfo(userinfo)
        return body, info


def parse_userinfo(header_value):
    """Parse a ``Subscription-Userinfo`` header into a dict.

    Format: ``upload=123; download=456; total=789; expire=1234567890``
    """
    info = {}
    if not header_value:
        return info
    for part in header_value.split(';'):
        part = part.strip()
        if '=' in part:
            k, v = part.split('=', 1)
            try:
                info[k.strip()] = int(v.strip())
            except ValueError:
                pass
    return info


def decode_body(body):
    """Decode response body: base64-unwrap if it looks like a URI list.

    Clash YAML responses are plain text — base64 decode fails or yields
    non-URI content, so the original text is returned unchanged.
    """
    try:
        text = body.decode('utf-8', errors='replace')
    except Exception:
        return ''
    # Only base64-unwrap when the decoded content looks like a URI list
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
