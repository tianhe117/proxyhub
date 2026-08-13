"""Port allocation.

Two disjoint ranges separate long-lived service ports from transient
test ports:

    service  50000-55000  long-running service SOCKS5 ports
    test     55000-60000  transient health-check ports
"""

import socket

from app.settings import (
    SOCKS_PORT_START, SOCKS_PORT_END,
    TEST_PORT_START, TEST_PORT_END,
)

_RANGES = {
    'service': (SOCKS_PORT_START, SOCKS_PORT_END),
    'test':    (TEST_PORT_START, TEST_PORT_END),
}

_cursor = {k: v[0] for k, v in _RANGES.items()}


def _available(port, host='127.0.0.1'):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.close()
        return True
    except OSError:
        return False


def allocate_ports(pool='service', n=1):
    """Return *n* available ports from the given pool.

    *pool* is 'service' (long-running) or 'test' (transient).
    A cursor advances after each call so consecutive allocations don't
    reuse recently-freed ports.
    """
    start, end = _RANGES[pool]
    cur = _cursor[pool]

    ports = []
    for port in range(cur, end):
        if len(ports) >= n:
            break
        if _available(port):
            ports.append(port)

    if len(ports) < n:
        for port in range(start, cur):
            if len(ports) >= n:
                break
            if _available(port):
                ports.append(port)

    if len(ports) < n:
        raise RuntimeError(
            f'Need {n} ports in [{start},{end}), only {len(ports)} available'
        )

    _cursor[pool] = ports[-1] + 1
    if _cursor[pool] >= end:
        _cursor[pool] = start
    return ports


def is_port_available(port, host='127.0.0.1'):
    """Check if a TCP port is available by attempting to bind."""
    return _available(port, host)
