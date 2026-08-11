"""Node health checking — high-level entry point.

check_node(node_ids, timeout=6)  → {node_id: CheckResult}
"""

from app.models.node import get_by_id
from app.models.setting import get_setting
from app.settings import DEFAULT_SETTINGS
from app.checker.checker import batch_check, CheckResult

__all__ = ['check_node', 'CheckResult']


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
        out[nid] = CheckResult(success=False, url_latency_ms=-1, tcp_latency_ms=-1,
                       http_code='0', error='Node not found')
    return out
