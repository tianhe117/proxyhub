#!/usr/bin/env python3
"""
test/test_checker.py — checker 测试

  1. tcp_check        — 纯 socket，零 DB 依赖
  2. url_check         — subprocess 调 proxy_url_check.sh
  3. _check_url_one    — config 生成 → url_check → 清理
  4. check_node        — 批量 TCP→URL 并发，从 DB 取节点

用法:
  python3 test/test_checker.py
"""

import json
import os
import sys
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.checker import check_node
from app.checker.checker import tcp_check, url_check
from app.utils import CheckResult
from app.checker.service import _check_url_one
from app.engine import build_outbound_config
from app.db.node import get_by_id
from app.utils import allocate_ports

TEST_URL = 'https://www.gstatic.com/generate_204'


def print_row(label, r):
    s = 'OK' if r.http_code == '204' else 'FAIL'
    print(f'  {label:<14} {s:<4}  tcp={r.tcp_latency_ms:>5}ms  '
          f'url={r.url_latency_ms:>5}ms  http={r.http_code:<6}  err={r.error}')


US  = None
V240 = None
V227 = None


def load_nodes():
    global US, V240, V227
    if US:
        return
    US = get_by_id(1187)
    V240 = get_by_id(1056)
    V227 = get_by_id(1059)


# ====================================================================
# 1. tcp_check
# ====================================================================

print('=' * 60)
print('1. tcp_check')
print('=' * 60)

load_nodes()

for nd in [US, V240, V227]:
    r = tcp_check(nd['address'], nd['port'], 3)
    status = 'ok' if r.success else 'FAIL'
    print(f'  {nd["name"][:14]:<14} {status:<5}  {r.tcp_latency_ms}ms')


# ====================================================================
# 2. url_check
# ====================================================================

print()
print('=' * 60)
print('2. url_check')
print('=' * 60)

ports = allocate_ports('test', 3)

for nd, port in zip([US, V240, V227], ports):
    config, _ = build_outbound_config(nd, port)
    fd, path = tempfile.mkstemp(prefix=f'test_url_{port}_', suffix='.json', dir='/tmp')
    with os.fdopen(fd, 'w') as f:
        json.dump(config, f)

    bin_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'bin', nd['bin_type'],
    )
    try:
        r = url_check(path, nd['bin_type'], bin_path, port,
                      TEST_URL, 5, f'test_{nd["id"]}')
        print_row(nd['name'][:14], r)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ====================================================================
# 3. _check_url_one
# ====================================================================

print()
print('=' * 60)
print('3. _check_url_one')
print('=' * 60)

ports = allocate_ports('test', 3)
for nd, port in zip([US, V240, V227], ports):
    r = _check_url_one(nd, port)
    print_row(nd['name'][:14], r)


# ====================================================================
# 4. check_node
# ====================================================================

print()
print('=' * 60)
print('4. check_node')
print('=' * 60)

nodes = [US, V240, V227,US, V240, V227,US, V240, V227,US, V240, V227]

t0 = time.time()
results = check_node(nodes)

for nd, r in zip(nodes, results):
    print_row(nd['name'][:14], r)

ok = sum(1 for r in results if r.http_code == '204')
print(f'\n  total={len(nodes)}  OK={ok}  FAIL={len(nodes)-ok}  {time.time()-t0:.1f}s')

print()
print('DONE')
