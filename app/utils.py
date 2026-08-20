"""Leaf utilities: pure helpers + latency store + log re-export.

Single import surface for callers:

    from app.utils import log, sha256, format_size, split_keywords
    from app.utils import is_valid_protocol, is_valid_inbound_protocol
    from app.utils import get_latency, update_latency, CheckResult

logger.py is a separate module (import-time side effect — creates the log
file); it is re-exported here so callers still use `from app.utils import log`.
"""

import hashlib
import threading
from dataclasses import dataclass

from app.logger import log
from app.settings import SUPPORTED_PROTOCOLS, VALID_INBOUND_PROTOCOLS


# ---------------------------------------------------------------------------
# Common pure helpers
# ---------------------------------------------------------------------------

def sha256(text):
    """Return the SHA-256 hex digest of a string."""
    return hashlib.sha256(text.encode()).hexdigest()


def format_size(num_bytes):
    """Format a byte count as a human-readable string (B / KB / MB / GB / TB).

    Returns a string with one decimal place, e.g. "1.2 GB".
    """
    if num_bytes is None:
        return '0 B'
    num_bytes = int(num_bytes)
    if num_bytes < 0:
        return '0 B'
    if num_bytes < 1024:
        return f'{num_bytes} B'
    for unit in ('KB', 'MB', 'GB', 'TB'):
        num_bytes /= 1024.0
        if num_bytes < 1024:
            return f'{num_bytes:.1f} {unit}'
    return f'{num_bytes:.1f} PB'


def split_keywords(text):
    """Split a keyword string by newline or comma into a list of trimmed tokens.

    Returns an empty list for None / empty / whitespace-only input.
    """
    if not text or not text.strip():
        return []
    tokens = []
    for chunk in text.replace('\r', '').split('\n'):
        for part in chunk.split(','):
            t = part.strip()
            if t:
                tokens.append(t)
    return tokens


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def is_valid_protocol(protocol):
    """Return True if *protocol* is a supported outbound protocol."""
    return protocol in SUPPORTED_PROTOCOLS


def is_valid_inbound_protocol(protocol):
    """Return True if *protocol* can be used as an inbound listener."""
    return protocol in VALID_INBOUND_PROTOCOLS


# ---------------------------------------------------------------------------
# Node latency in-memory store
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    success: bool
    tcp_latency_ms: int       # TCP handshake latency (-1 if failed)
    url_latency_ms: int       # URL latency (-1 if not done)
    http_code: str            # URL HTTP code ("0" if not done)
    error: str


_lock = threading.Lock()   # 互斥锁（非队列）：写是纳秒级赋值，last-write-wins 即可
_latency = {}  # {node_id: CheckResult}


def get_latency(node_id: int) -> CheckResult | None:
    """Return the node's latest CheckResult, or None if never checked."""
    with _lock:
        return _latency.get(node_id)


def update_latency(node_id: int, result: CheckResult) -> None:
    """Store (or overwrite) the CheckResult for *node_id*."""
    with _lock:
        _latency[node_id] = result


__all__ = [
    'log',
    'sha256', 'format_size', 'split_keywords',
    'is_valid_protocol', 'is_valid_inbound_protocol',
    'CheckResult', 'get_latency', 'update_latency',
]
