"""Subscription parser package: URI list + Clash YAML → node dicts.

Pure functions, zero DB/IO dependency. The single public entry is
``parse_all(raw_text, include, exclude)``; per-protocol modules expose
``parse_uri(uri)`` and ``clash.parse_yaml(text)`` is used internally.

Adding a new protocol:
    1. create ``app/parser/{protocol}.py`` with ``parse_uri(uri)``
    2. add a branch in ``_dispatch_uri`` below
    3. add the string to ``config.SUPPORTED_PROTOCOLS``
"""

from app.utils import log

from . import base, clash, ss, vmess, vless, trojan, hysteria2, tuic

__all__ = ['parse_all']


# URI prefix → parser module
_URI_DISPATCH = {
    'ss://':          ss,
    'vmess://':       vmess,
    'vless://':       vless,
    'trojan://':      trojan,
    'hy2://':         hysteria2,
    'hysteria2://':   hysteria2,
    'hysteria://':    hysteria2,
    'tuic://':        tuic,
}


def parse_all(raw_text, include='', exclude=''):
    """Parse subscription text into a list of node dicts.

    Detects format: Clash YAML (``proxies:`` or ``mixed-port:``) vs a plain
    URI list (optionally base64-wrapped). Applies keyword filtering, then
    dedups by name (last occurrence wins).

    Single-parse failures are logged and skipped — one bad line never aborts
    the whole batch.
    """
    if not raw_text or not raw_text.strip():
        return []

    text = base.decode_base64(raw_text)
    stripped = text.strip()

    if _looks_like_clash_yaml(stripped):
        nodes = clash.parse_yaml(stripped)
    else:
        nodes = _parse_uri_lines(stripped)

    # Keyword filter
    if include or exclude:
        nodes = _filter_nodes(nodes, include, exclude)

    # Dedup by name (last wins)
    seen = {}
    for n in nodes:
        seen[n['name']] = n
    return list(seen.values())


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _looks_like_clash_yaml(text):
    """Heuristic: Clash configs have a top-level proxies: or mixed-port:."""
    head = text[:512].lower()
    return 'proxies:' in head or 'mixed-port:' in head


def _parse_uri_lines(text):
    """Parse a plain URI list (one node per line)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    nodes = []
    for line in lines:
        mod = _dispatch_uri(line)
        if mod is None:
            continue
        try:
            node = mod.parse_uri(line)
            if node:
                nodes.append(node)
        except Exception as e:
            log.warning(f'parse failed, skip: {line[:60]}... — {e}')
    return nodes


def _dispatch_uri(line):
    for prefix, mod in _URI_DISPATCH.items():
        if line.startswith(prefix):
            return mod
    # Unknown / non-proxy line — skip silently (URI lists may carry comments)
    return None


def _filter_nodes(nodes, include, exclude):
    """Filter nodes by keyword matching on name (OR logic, case-insensitive)."""
    from app.utils import split_keywords
    f_kw = split_keywords(include)
    e_kw = split_keywords(exclude)
    if not f_kw and not e_kw:
        return nodes
    out = []
    for n in nodes:
        name = (n.get('name') or '').lower()
        if f_kw and not any(kw.lower() in name for kw in f_kw):
            continue
        if e_kw and any(kw.lower() in name for kw in e_kw):
            continue
        out.append(n)
    return out
