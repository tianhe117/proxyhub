"""clash_api client: /delay, GET/PUT /proxies.

Reaches the resident sing-box clash_api at 127.0.0.1:{clash_api_port}.
All functions tolerate a non-running sing-box / network errors — they
return an error-bearing dict or False instead of raising, so callers
(checker / scheduler) decide how to handle failures.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from app.settings import get_setting

CLASH_API_HOST = '127.0.0.1'


def _base_url():
    """Return the clash_api base URL (port from settings)."""
    port = get_setting('clash_api_port')
    return f'http://{CLASH_API_HOST}:{port}'


def _request(method, path, body=None, timeout=None):
    """Issue a clash_api request; return (status_code, parsed_json | error_str).

    Returns (None, error_str) when sing-box is not reachable.
    """
    url = _base_url() + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=timeout or 5) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, raw.decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        # clash_api returns 4xx/5xx with a JSON body for failures
        try:
            payload = json.loads(e.read())
        except Exception:
            payload = str(e)
        return e.code, payload
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        return None, str(e)


def get_delay(node_name, url, timeout):
    """GET /proxies/{node}/delay?url=...&timeout=...

    Returns:
        dict: {"delay": N} on success, {"error": "..."} on failure.
    """
    tag = urllib.parse.quote(node_name, safe='')
    query = urllib.parse.urlencode({'url': url, 'timeout': timeout})
    status, body = _request('GET', f'/proxies/{tag}/delay?{query}',
                            timeout=int(get_setting('curl_timeout')))
    if status is None:
        return {'error': body}
    if status == 200 and isinstance(body, dict) and 'delay' in body:
        return {'delay': body['delay']}
    # clash_api returns {"message": "..."} on failure
    msg = body.get('message') if isinstance(body, dict) else str(body)
    return {'error': msg or f'HTTP {status}'}


def get_proxies():
    """GET /proxies → full proxy map (includes each selector's ``now``).

    Returns:
        dict: {"proxies": {...}} on success, {"error": "..."} on failure.
    """
    status, body = _request('GET', '/proxies')
    if status is None:
        return {'error': body}
    if status == 200 and isinstance(body, dict):
        return body
    return {'error': f'HTTP {status}'}


def select_proxy(group, node):
    """PUT /proxies/{group} body {"name": node} → switch selector.

    Returns:
        bool: True on success, False on failure.
    """
    tag = urllib.parse.quote(group, safe='')
    status, _ = _request('PUT', f'/proxies/{tag}', body={'name': node})
    return status == 204 or status == 200


def get_proxy_now(group):
    """GET /proxies/{group} → return the current ``now`` tag, or None.

    None means the group doesn't exist or sing-box is unreachable.
    """
    tag = urllib.parse.quote(group, safe='')
    status, body = _request('GET', f'/proxies/{tag}')
    if status == 200 and isinstance(body, dict):
        return body.get('now')
    return None
