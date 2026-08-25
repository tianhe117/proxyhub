"""Node health-check business service.

Owns single/batch check orchestration, task progress, and the in-memory
latency store.  The Web layer only adapts request/response data.
"""

import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from app.db import node as db_node
from app.services.runtime import apply_config, start_singbox
from app.settings import get_setting
from app.singbox import is_running as sb_is_running
from app.singbox import restart as sb_restart
from app.singbox.clash import get_delay
from app.utils import log


MAX_WORKERS = 10


@dataclass
class CheckResult:
    tcp_latency_ms: int
    url_latency_ms: int
    error: str


_latencies = {}  # {node_id: CheckResult}
_latencies_lock = threading.Lock()

_tasks = {}  # {task_id: {status, total, completed, results}}
_tasks_lock = threading.Lock()


def get_latency(node_id: int) -> CheckResult | None:
    """Return a node's latest result, or None if it has not been checked."""
    with _latencies_lock:
        return _latencies.get(node_id)


def get_all_latencies() -> dict[int, CheckResult]:
    """Return a snapshot of all latest node check results."""
    with _latencies_lock:
        return dict(_latencies)


def update_latency(node_id: int, result: CheckResult) -> None:
    """Store or replace a node's latest check result."""
    with _latencies_lock:
        _latencies[node_id] = result


def get_task(task_id):
    """Return batch-check progress, or None when the task does not exist."""
    with _tasks_lock:
        return _tasks.get(task_id)


def start_check(data=None):
    """Resolve a node selection and start a single or batch health check."""
    _ensure_singbox_with_nodes()
    data = data or {}

    if 'node_id' in data:
        node_list = _resolve_node_ids([data['node_id']])
    elif 'node_ids' in data:
        node_list = _resolve_node_ids(data['node_ids'])
    elif 'sub_id' in data:
        node_list = _resolve_sub_nodes(data['sub_id'])
    else:
        node_list = _resolve_all_nodes()

    if not node_list:
        return {'success': False, 'message': 'No nodes to check'}

    if len(node_list) == 1:
        node_id, address, port = node_list[0]
        result = check_node(node_id, address, port)
        return {
            'single': True,
            'node_id': node_id,
            'result': _result_dict(result),
        }

    task_id = f'chk_{int(time.time())}_{uuid.uuid4().hex[:6]}'
    threading.Thread(
        target=check_nodes_async,
        args=(node_list, task_id),
        daemon=True,
    ).start()
    return {'task_id': task_id, 'total': len(node_list), 'status': 'running'}


def check_node(node_id, address, port):
    """Run TCP and URL checks for one node and store the latest result."""
    tcp_timeout = int(get_setting('tcp_timeout'))
    tcp_ms = _tcp_check(address, port, tcp_timeout)
    if tcp_ms < 0:
        result = CheckResult(
            tcp_latency_ms=-1,
            url_latency_ms=-1,
            error=f'tcp: timeout ({tcp_timeout}s)',
        )
        update_latency(node_id, result)
        return result

    test_url = get_setting('test_url')
    url_timeout = int(get_setting('curl_timeout')) * 1000
    delay = get_delay(f'n{node_id}', test_url, url_timeout)
    if 'delay' in delay:
        result = CheckResult(
            tcp_latency_ms=tcp_ms,
            url_latency_ms=delay['delay'],
            error='',
        )
    else:
        result = CheckResult(
            tcp_latency_ms=tcp_ms,
            url_latency_ms=-1,
            error=f'url: {delay.get("error", "unknown")}',
        )
    update_latency(node_id, result)
    return result


def check_nodes_async(node_list, task_id):
    """Check multiple nodes concurrently and update task progress."""
    _init_task(task_id, len(node_list))
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(check_node, node_id, address, port): node_id
            for node_id, address, port in node_list
        }
        for future in as_completed(futures):
            node_id = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = CheckResult(-1, -1, str(error))
                update_latency(node_id, result)
            _update_task(task_id, node_id, result)
    _finish_task(task_id)


def _ensure_singbox_with_nodes():
    if not sb_is_running():
        start_singbox()
    else:
        apply_config()
        sb_restart()


def _resolve_node_ids(node_ids):
    result = []
    for node_id in node_ids:
        node = db_node.get_by_id(node_id)
        if node:
            result.append((node['id'], node['address'], node['port']))
    return result


def _resolve_sub_nodes(sub_id):
    return [
        (node['id'], node['address'], node['port'])
        for node in db_node.list_by_sub(sub_id)
    ]


def _resolve_all_nodes():
    return [
        (node['id'], node['address'], node['port'])
        for node in db_node.list_all()
    ]


def _tcp_check(address, port, timeout):
    try:
        started = time.monotonic()
        with socket.create_connection((address, port), timeout=timeout):
            return int((time.monotonic() - started) * 1000)
    except (socket.timeout, OSError):
        return -1


def _result_dict(result):
    return {
        'tcp_latency_ms': result.tcp_latency_ms,
        'url_latency_ms': result.url_latency_ms,
        'error': result.error,
    }


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
        task = _tasks.get(task_id)
        if not task:
            return
        task['results'][str(node_id)] = _result_dict(result)
        task['completed'] = len(task['results'])


def _finish_task(task_id):
    with _tasks_lock:
        task = _tasks.get(task_id)
        if task:
            task['status'] = 'done'
