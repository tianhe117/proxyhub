"""Parser shared helpers: base64 decode, keyword filter, query parser.

Pure functions, zero dependencies on app.* (except utils.split_keywords).
"""

import base64
import urllib.parse

from app.utils import split_keywords


def decode_base64(text):
    """Best-effort base64 decode (URL-safe then standard); return decoded text
    if it contains proxy URI markers, else return the original text.

    Tolerant: bad padding / non-base64 input returns the original text so the
    caller can still try to parse it line-by-line.
    """
    try:
        padded = text
        missing = len(padded) % 4
        if missing:
            padded += '=' * (4 - missing)
        # URL-safe first, then standard
        try:
            decoded = base64.urlsafe_b64decode(padded).decode('utf-8', errors='replace')
        except Exception:
            decoded = base64.b64decode(padded).decode('utf-8', errors='replace')
        if 'vmess://' in decoded or 'ss://' in decoded or 'vless://' in decoded:
            return decoded
    except Exception:
        pass
    return text


def filter_lines(lines, include, exclude):
    """Filter URI lines by include/exclude keywords (OR logic).

    - include: if set, a line's text must contain at least one keyword to keep
    - exclude: if any keyword matches, the line is dropped
    Keyword matching is case-insensitive on the raw line text.
    """
    f_kw = split_keywords(include)
    e_kw = split_keywords(exclude)
    if not f_kw and not e_kw:
        return list(lines)

    out = []
    for line in lines:
        low = line.lower()
        if f_kw and not any(kw.lower() in low for kw in f_kw):
            continue
        if e_kw and any(kw.lower() in low for kw in e_kw):
            continue
        out.append(line)
    return out


def parse_kv_params(query):
    """Parse a URL query string (``?k=v&k2=v2``) into a dict.

    Returns single values; repeated keys collapse to the last occurrence.
    """
    return {k: v[-1] for k, v in urllib.parse.parse_qs(query, keep_blank_values=True).items()}
