"""Node latency in-memory store.

Latency is not persisted — it resets on app start. The frontend shows "—"
for nodes that have never been checked (get_latency returns None).

Keyed by node id, the store holds the full CheckResult so callers choose
which fields to surface:

    get_latency(node_id)           → CheckResult | None
    update_latency(node_id, result) → None
"""

import threading

from .schemas import CheckResult

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
