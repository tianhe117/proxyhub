"""Node health checking — business orchestration.

check_node(nodes, timeout=6)  → list[CheckResult]
"""

import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.engine import build_outbound_config
from app.settings import DEFAULT_SETTINGS, get_bin_dir, get_setting
from app.checker.checker import tcp_check, url_check
from app.utils import CheckResult
from app.utils import allocate_ports


# ---------------------------------------------------------------------------
# _check_url_one  —  config 生成 → url_check → 清理
# ---------------------------------------------------------------------------

def _check_url_one(node: dict, port: int) -> CheckResult:
    """Generate temp proxy config → url_check → cleanup.

    Settings (test_url, timeout) are read from DB inside this function.
    *port* is allocated by the caller.
    """
    curl_to = int(get_setting('curl_timeout') or DEFAULT_SETTINGS['curl_timeout'])
    test_url = get_setting('test_url') or DEFAULT_SETTINGS['test_url']
    tag = f'ph_{node["id"]}'

    try:
        config = build_outbound_config(node, port)
    except Exception as e:
        return CheckResult(success=False, url_latency_ms=-1, tcp_latency_ms=-1,
                           http_code='0', error=f'config generation failed: {e}')

    fd, path = tempfile.mkstemp(prefix=f'ph_check_{port}_', suffix='.json', dir='/tmp')
    with os.fdopen(fd, 'w') as f:
        json.dump(config, f)
    try:
        bin_path = os.path.join(get_bin_dir(), node['bin_type'])
        return url_check(path, node['bin_type'], bin_path, port,
                         test_url, curl_to, tag)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# check_node  —  TCP → URL 两阶段并发
# ---------------------------------------------------------------------------

def check_node(nodes: list[dict], timeout=None) -> list[CheckResult]:
    """Health-check a list of node dicts: TCP first (all parallel),
    then URL for nodes that passed TCP (parallel).

    Nodes that fail TCP are skipped for URL.
    """
    if not nodes:
        return []

    tcp_to = int(get_setting('tcp_timeout') or DEFAULT_SETTINGS['tcp_timeout'])
    curl_to = int(get_setting('curl_timeout') or DEFAULT_SETTINGS['curl_timeout'])
    timeout = timeout or curl_to

    n = len(nodes)

    # ---- phase 1: TCP (all parallel) ----
    tcp_results = [None] * n
    with ThreadPoolExecutor(max_workers=n) as ex:
        futures = {
            ex.submit(tcp_check, nd['address'], nd['port'], tcp_to): i
            for i, nd in enumerate(nodes)
        }
        for fut in as_completed(futures):
            tcp_results[futures[fut]] = fut.result()

    # ---- phase 2: URL (skip TCP failures) ----
    url_items = [(i, nd) for i, nd in enumerate(nodes) if tcp_results[i].success]
    url_results = {i: None for i, _ in url_items}
    if url_items:
        ports = allocate_ports('test', len(url_items))
        with ThreadPoolExecutor(max_workers=len(url_items)) as ex:
            futures = {}
            for (i, nd), port in zip(url_items, ports):
                fut = ex.submit(_check_url_one, nd, port)
                futures[fut] = i
            for fut in as_completed(futures):
                i = futures[fut]
                url_results[i] = fut.result()

    # ---- merge ----
    out = []
    for i, nd in enumerate(nodes):
        tcp = tcp_results[i]
        url = url_results.get(i)
        if url is None:
            out.append(CheckResult(success=tcp.success, url_latency_ms=-1,
                           tcp_latency_ms=tcp.tcp_latency_ms,
                           http_code='0', error=tcp.error))
        else:
            out.append(CheckResult(success=url.success, url_latency_ms=url.url_latency_ms,
                           tcp_latency_ms=tcp.tcp_latency_ms,
                           http_code=url.http_code, error=url.error))
    return out
