"""Node health checking — TCP + URL detection for proxy nodes.

Public API
----------
check_node(node_ids, timeout=6)  → {node_id: Res}
batch_check(node_list, timeout=6) → [Res]          (* lower-level, no DB *)

Lower-level helpers (no DB dependency)
---------------------------------------
tcp_check(address, port, timeout=3)  → Res
url_check(node_dict, port, url, timeout, tag) → Res
allocate_ports(n) → list[int]
"""

import json
import os
import socket
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from app.models.node import get_by_id
from app.models.setting import get_setting
from app.settings import DEFAULT_SETTINGS
from app.engine import build_outbound_config

__all__ = ['check_node', 'batch_check', 'tcp_check', 'url_check', 'allocate_ports', 'Res']


# ============================================================================
# Res
# ============================================================================

@dataclass
class Res:
    success: bool
    latency_ms: int           # URL latency (-1 if not done)
    tcp_latency_ms: int       # TCP handshake latency (-1 if failed)
    http_code: str            # URL HTTP code ("0" if not done)
    error: str


# ============================================================================
# port allocation
# ============================================================================

_PORT_MIN = 50000
_PORT_MAX = 60000
_cursor   = _PORT_MIN


def allocate_ports(n: int) -> list[int]:
    """Return *n* available ports starting from the last-used cursor.

    The cursor wraps to _PORT_MIN when it reaches _PORT_MAX so
    consecutive calls don't reuse recently-freed ports.
    """
    global _cursor

    ports = []
    for port in range(_cursor, _PORT_MAX):
        if len(ports) >= n: break
        if _try_port(port): ports.append(port)

    if len(ports) < n:
        for port in range(_PORT_MIN, _cursor):
            if len(ports) >= n: break
            if _try_port(port): ports.append(port)

    if len(ports) < n:
        raise RuntimeError(f'Need {n} ports in [{_PORT_MIN},{_PORT_MAX}), only {len(ports)} available')

    _cursor = ports[-1] + 1
    if _cursor >= _PORT_MAX:
        _cursor = _PORT_MIN
    return ports


def _try_port(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', port))
        s.close()
        return True
    except OSError:
        return False


# ============================================================================
# TCP check  (pure Python, zero subprocess)
# ============================================================================

def tcp_check(address: str, port: int, timeout: int = 3) -> Res:
    try:
        t0 = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((address, int(port)))
        lat = round((time.time() - t0) * 1000)
        sock.close()
        return Res(success=True, latency_ms=-1, tcp_latency_ms=lat,
                   http_code='0', error='')
    except Exception as e:
        return Res(success=False, latency_ms=-1, tcp_latency_ms=-1,
                   http_code='0', error=str(e))


# ============================================================================
# URL check  (subprocess → proxy_url_check.sh)
# ============================================================================

_SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'scripts',
)

_BIN_EXE = {'xray': 'xray', 'sslocal': 'sslocal', 'sing-box': 'sing-box'}


def url_check(node: dict, port: int, test_url: str, timeout: int, tag: str) -> Res:
    """Run a URL reachability test through a proxy.

    1. Generate temp proxy config from *node* on *port*.
    2. Call proxy_url_check.sh.
    3. Parse stdout JSON → Res.
    4. Delete temp config.
    """
    config_path = _write_config(node, port)
    try:
        return _run(config_path, node['bin_type'], port, test_url, timeout, tag)
    finally:
        _rm(config_path)


def _write_config(node: dict, port: int) -> str:
    config, _ = build_outbound_config(node, port)
    fd, path = tempfile.mkstemp(prefix='ph_check_', suffix='.json', dir='/tmp')
    with os.fdopen(fd, 'w') as f:
        json.dump(config, f)
    return path


def _run(config_path: str, bin_type: str, port: int,
         test_url: str, timeout: int, tag: str) -> Res:
    script   = os.path.join(_SCRIPTS_DIR, 'proxy_url_check.sh')
    bin_path = os.path.join(_SCRIPTS_DIR, '..', 'bin', _BIN_EXE[bin_type])

    try:
        result = subprocess.run(
            ['bash', script, config_path, bin_type, bin_path,
             str(port), test_url, str(timeout), tag],
            capture_output=True, text=True, timeout=timeout + 30,
        )
        out = (result.stdout or '').strip()
        if out:
            data = json.loads(out)
            return Res(
                success=(result.returncode == 0),
                latency_ms=data.get('latency_ms', -1),
                tcp_latency_ms=-1,
                http_code=data.get('http_code', '0'),
                error=data.get('error', ''),
            )
        return Res(success=False, latency_ms=-1, tcp_latency_ms=-1,
                   http_code='0', error=result.stderr or 'No output')
    except subprocess.TimeoutExpired:
        return Res(success=False, latency_ms=-1, tcp_latency_ms=-1,
                   http_code='0', error='URL check timed out')
    except json.JSONDecodeError:
        return Res(success=False, latency_ms=-1, tcp_latency_ms=-1,
                   http_code='0', error='Invalid JSON from proxy_url_check.sh')


def _rm(path: str):
    try:
        os.remove(path)
    except OSError:
        pass


# ============================================================================
# batch_check — low-level, no DB dependency
# ============================================================================

def batch_check(nodes: list[dict], test_url: str = '',
                tcp_timeout: int = 3, curl_timeout: int = 6,
                strict: bool = True) -> list[Res]:
    """Run TCP→URL on a list of node dicts in parallel.

    *strict*: when True, skip URL for nodes that fail TCP.
    """
    n = len(nodes)
    if not n:
        return []

    # ---- phase 1: TCP (all parallel) ----
    tcp_results = [None] * n
    with ThreadPoolExecutor(max_workers=n) as ex:
        futures = {
            ex.submit(tcp_check, nd['address'], nd['port'], tcp_timeout): i
            for i, nd in enumerate(nodes)
        }
        for fut in as_completed(futures):
            tcp_results[futures[fut]] = fut.result()

    # ---- phase 2: URL (skip TCP failures) ----
    url_items = [(i, nd) for i, nd in enumerate(nodes)
                 if not strict or tcp_results[i].success]
    url_results = {i: None for i, _ in url_items}
    if url_items:
        ports = allocate_ports(len(url_items))
        with ThreadPoolExecutor(max_workers=len(url_items)) as ex:
            futures = {}
            for (i, nd), port in zip(url_items, ports):
                tag = f'ph_{nd["id"]}'
                fut = ex.submit(url_check, nd, port, test_url, curl_timeout, tag)
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
            # URL not performed (TCP failed or strict=False)
            out.append(Res(success=tcp.success, latency_ms=-1,
                           tcp_latency_ms=tcp.tcp_latency_ms,
                           http_code='0', error=tcp.error))
        else:
            out.append(Res(success=url.success, latency_ms=url.latency_ms,
                           tcp_latency_ms=tcp.tcp_latency_ms,
                           http_code=url.http_code, error=url.error))
    return out


# ============================================================================
# check_node — high-level, node_id → DB → batch_check
# ============================================================================

def check_node(node_ids, timeout=None):
    """Health-check one or more nodes by DB id.

    Accepts int | list[int].  Reads settings from DB (test_url, timeouts).
    """
    if isinstance(node_ids, int):
        node_ids = [node_ids]

    tcp_to = int(get_setting('tcp_timeout') or DEFAULT_SETTINGS['tcp_timeout'])
    curl_to = int(get_setting('curl_timeout') or DEFAULT_SETTINGS['curl_timeout'])
    url = get_setting('test_url') or DEFAULT_SETTINGS['test_url']
    timeout = timeout or curl_to

    nodes = []
    missing = []
    for nid in node_ids:
        nd = get_by_id(nid)
        if nd:
            nodes.append(nd)
        else:
            missing.append(nid)

    results = batch_check(nodes, test_url=url, tcp_timeout=tcp_to,
                          curl_timeout=timeout, strict=True)

    out = {}
    for i, nd in enumerate(nodes):
        out[nd['id']] = results[i]
    for nid in missing:
        out[nid] = Res(success=False, latency_ms=-1, tcp_latency_ms=-1,
                       http_code='0', error='Node not found')
    return out
