"""Node health checking orchestration (§5.5).

Coordinates TCP ping and URL testing across multiple nodes, runs in a
background thread, and exposes progress via a global task dict.
"""

import json
import os
import threading
import time
import uuid
from datetime import datetime

from app.models.node import get_by_id, update_latency, list_all
from app.models.setting import get_setting
from app.settings import get_bin_dir, get_config_dir
from app.checker.script import tcp_ping, url_test
from app.logger import log

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
_check_lock = threading.Lock()
_tasks = {}  # task_id → {running, total, checked, nodes: {id: result}}


def check_nodes(node_ids=None, check_type='both'):
    """Start a health check task.

    Args:
        node_ids: list of node IDs, or None for all nodes
        check_type: 'tcp' | 'url' | 'both'

    Returns:
        dict: {success, task_id?, message}
    """
    # Global lock — only one check task at a time
    if not _check_lock.acquire(blocking=False):
        return {'success': False, 'message': 'A check task is already running'}

    # Get nodes
    if node_ids:
        nodes = [n for n in (get_by_id(nid) for nid in node_ids) if n]
    else:
        nodes = list_all()

    if not nodes:
        _check_lock.release()
        return {'success': False, 'message': 'No nodes to check'}

    task_id = str(uuid.uuid4())[:8]

    # Init task state
    node_results = {}
    for n in nodes:
        node_results[n['id']] = {'tcp': None, 'url': None}
    _tasks[task_id] = {
        'running': True,
        'total': len(nodes),
        'checked': 0,
        'nodes': node_results,
    }

    # Run in background thread
    t = threading.Thread(
        target=_run_checks, args=(task_id, nodes, node_results, check_type),
        daemon=True
    )
    t.start()

    return {'success': True, 'task_id': task_id,
            'message': f'Check started for {len(nodes)} nodes'}


def get_check_status(task_id):
    """Return the current status of a check task."""
    task = _tasks.get(task_id)
    if not task:
        return {'running': False, 'message': 'Task not found'}
    return task


def _run_checks(task_id, nodes, results, check_type):
    """Background thread: run checks on each node."""
    tcp_timeout = int(get_setting('tcp_timeout') or 3)
    curl_timeout = int(get_setting('curl_timeout') or 5)
    test_url = get_setting('test_url') or 'http://www.gstatic.com/generate_204'

    try:
        for node in nodes:
            tag = f'ph_{node["id"]}_{int(time.time())}'

            # TCP ping
            if check_type in ('tcp', 'both'):
                try:
                    res = tcp_ping(node['address'], node['port'], tcp_timeout, tag)
                    results[node['id']]['tcp'] = res
                except Exception as e:
                    results[node['id']]['tcp'] = {'success': False, 'error': str(e)}

            # URL test (only if TCP succeeded or doing url-only)
            if check_type == 'url' or (check_type == 'both' and results[node['id']]['tcp'] and results[node['id']]['tcp'].get('success')):
                # Generate temp config
                try:
                    local_port = _find_temp_port()
                    config_path = _generate_temp_config(node, local_port)
                    bin_type = node['bin_type']
                    bin_key = f'bin_path_{bin_type if bin_type != "sing-box" else "singbox"}'
                    bin_path = get_setting(bin_key) or ''
                    if bin_path and not os.path.isabs(bin_path):
                        bin_path = os.path.join(
                            os.path.dirname(os.path.dirname(os.path.dirname(
                                os.path.abspath(__file__)))), bin_path
                        )

                    res = url_test(config_path, bin_type, bin_path,
                                   local_port, test_url, curl_timeout, tag)
                    results[node['id']]['url'] = res
                except Exception as e:
                    results[node['id']]['url'] = {'success': False, 'error': str(e)}
                finally:
                    # Cleanup temp config
                    try:
                        if 'config_path' in dir() and os.path.exists(config_path):
                            os.remove(config_path)
                    except Exception:
                        pass

            # Update DB latency
            tcp = results[node['id']].get('tcp', {}) or {}
            url = results[node['id']].get('url', {}) or {}

            tcp_lat = tcp.get('latency_ms', -1) if tcp.get('success') else -1
            curl_lat = url.get('latency_ms', -1) if url.get('success') else -1

            update_latency(node['id'], tcp_lat, curl_lat,
                           datetime.now().isoformat())

            # Update progress
            _tasks[task_id]['checked'] += 1

    finally:
        _tasks[task_id]['running'] = False
        _check_lock.release()
        log('ok', 'checker', f'Check task {task_id} completed')


def _generate_temp_config(node, local_port):
    """Generate a minimal temp config file for URL testing.

    Returns the absolute path to the config file.
    """
    import json as _json
    from app.engine import build_outbound_config

    config, _ = build_outbound_config(node, local_port)

    tmp_path = os.path.join('/tmp', f'ph_test_{node["id"]}_{int(time.time())}.json')
    with open(tmp_path, 'w') as f:
        _json.dump(config, f)
    return tmp_path


def _find_temp_port():
    """Find a random available port for temp testing."""
    import random
    import socket
    for _ in range(50):
        port = random.randint(50000, 60000)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(('127.0.0.1', port))
            s.close()
            return port
        except OSError:
            continue
    raise RuntimeError('No available port for URL testing')
