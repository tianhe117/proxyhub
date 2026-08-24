"""Node health checker: TCP + clash_api URL test.

Single-node: check_node(node_id, address, port) → CheckResult
Batch:       check_nodes_async(node_list, task_id) → writes to _tasks

Both write results to the in-memory latency store (app.utils).
"""

import socket
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.utils import CheckResult, update_latency, log
from app.singbox.clash import get_delay
from app.settings import get_setting

MAX_WORKERS = 10

# Task store — batch test progress, keyed by task_id
_tasks = {}        # {task_id: {status, total, completed, results}}
_tasks_lock = threading.Lock()


def check_node(node_id, address, port):
    """Test a single node: TCP → URL → CheckResult → write latency store.

    Returns CheckResult.
    """
    tcp_timeout = int(get_setting('tcp_timeout'))
    tcp_ms = _tcp_check(address, port, tcp_timeout)
    if tcp_ms < 0:
        result = CheckResult(
            tcp_latency_ms=-1, url_latency_ms=-1,
            error=f'tcp: timeout ({tcp_timeout}s)')
        update_latency(node_id, result)
        return result

    test_url = get_setting('test_url')
    url_timeout = int(get_setting('curl_timeout')) * 1000
    r = get_delay(f'n{node_id}', test_url, url_timeout)
    if 'delay' in r:
        result = CheckResult(tcp_latency_ms=tcp_ms, url_latency_ms=r['delay'], error='')
    else:
        result = CheckResult(
            tcp_latency_ms=tcp_ms, url_latency_ms=-1,
            error=f'url: {r.get("error", "unknown")}')
    update_latency(node_id, result)
    return result


def check_nodes_async(node_list, task_id):
    """Batch test with ThreadPoolExecutor. Results written to _tasks + latency store.

    Args:
        node_list: [(node_id, address, port), ...]
        task_id: unique identifier for this batch
    """
    _init_task(task_id, len(node_list))
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        for nid, addr, port in node_list:
            f = pool.submit(check_node, nid, addr, port)
            futures[f] = nid
        for f in as_completed(futures):
            nid = futures[f]
            try:
                result = f.result()
            except Exception as e:
                result = CheckResult(tcp_latency_ms=-1, url_latency_ms=-1, error=str(e))
                update_latency(nid, result)
            _update_task(task_id, nid, result)
    _finish_task(task_id)


def get_task(task_id):
    """Return task progress dict, or None if not found."""
    with _tasks_lock:
        return _tasks.get(task_id)


def _tcp_check(addr, port, timeout):
    """TCP handshake timing. Returns ms on success, -1 on failure."""
    try:
        start = time.monotonic()
        with socket.create_connection((addr, port), timeout=timeout):
            return int((time.monotonic() - start) * 1000)
    except (socket.timeout, OSError):
        return -1


def _init_task(task_id, total):
    with _tasks_lock:
        _tasks[task_id] = {
            'status': 'running',
            'total': total,
            'completed': 0,
            'results': {},
        }


def _update_task(task_id, node_id, result):
    with _tasks_lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t['results'][str(node_id)] = {
            'tcp_latency_ms': result.tcp_latency_ms,
            'url_latency_ms': result.url_latency_ms,
            'error': result.error,
        }
        t['completed'] = len(t['results'])


def _finish_task(task_id):
    with _tasks_lock:
        t = _tasks.get(task_id)
        if t:
            t['status'] = 'done'
