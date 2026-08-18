#!/usr/bin/env python3
"""Smoke-test for sing-box process management.

Tests: is_running → start → connectivity → stop → restart → stop.
Requires: data/config.json with valid outbound, data/bin/sing-box binary.
"""

import sys
import os
import time
import urllib.request

# Ensure project root on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.singbox import start, stop, restart, is_running
from app.settings import CONFIG_PATH, SINGBOX_BIN_PATH

PROXY = 'http://127.0.0.1:1080'
TEST_URL = 'https://www.google.com/generate_204'
TIMEOUT = 10


def _check(label, ok):
    status = '✓' if ok else '✗'
    print(f'  {status} {label}')
    if not ok:
        sys.exit(1)


def _test_connectivity():
    """Request Google through the local proxy, expect 204."""
    try:
        proxy_handler = urllib.request.ProxyHandler({
            'http': PROXY,
            'https': PROXY,
        })
        opener = urllib.request.build_opener(proxy_handler)
        req = urllib.request.Request(TEST_URL)
        with opener.open(req, timeout=TIMEOUT) as resp:
            return resp.status == 204
    except Exception as e:
        print(f'    connectivity error: {e}')
        return False


def _show(label, result):
    print(f'\n--- {label} ---')
    print(f'  result: {result}')


def main():
    # Pre-flight checks
    print('=== Pre-flight ===')
    _check(f'binary exists: {SINGBOX_BIN_PATH}',
           os.path.isfile(SINGBOX_BIN_PATH))
    _check(f'config exists: {CONFIG_PATH}',
           os.path.isfile(CONFIG_PATH))

    # 1. is_running (should be False initially)
    print('\n--- 1. is_running (before start) ---')
    running = is_running()
    _check('not running', not running)

    # 2. start
    print('\n--- 2. start ---')
    try:
        pid = start()
        _check(f'got pid: {pid}', pid is not None and pid > 0)
    except Exception as e:
        print(f'  start failed: {e}')
        sys.exit(1)

    # 3. is_running (should be True now)
    print('\n--- 3. is_running (after start) ---')
    running = is_running()
    _check('running', running)

    # 4. start again (idempotent)
    print('\n--- 4. start (idempotent) ---')
    pid2 = start()
    _check(f'same pid: {pid2} == {pid}', pid2 == pid)

    # 5. connectivity via proxy
    print(f'\n--- 5. connectivity ({PROXY} → {TEST_URL}) ---')
    time.sleep(0.5)  # brief settle
    ok = _test_connectivity()
    _check('HTTP 204 from Google', ok)

    # 6. stop
    print('\n--- 6. stop ---')
    result = stop()
    _check(f'stop success: {result}', result['success'])
    time.sleep(0.3)

    # 7. is_running (should be False)
    print('\n--- 7. is_running (after stop) ---')
    running = is_running()
    _check('not running', not running)

    # 8. restart
    print('\n--- 8. restart ---')
    result = restart()
    _check(f'restart success: {result}', result['success'])
    time.sleep(0.5)

    # 9. is_running (should be True)
    print('\n--- 9. is_running (after restart) ---')
    running = is_running()
    _check('running', running)

    # 10. connectivity after restart
    print(f'\n--- 10. connectivity after restart ---')
    ok = _test_connectivity()
    _check('HTTP 204 from Google', ok)

    # Cleanup
    print('\n--- cleanup: stop ---')
    stop()
    _check('stopped', not is_running())

    print('\n=== ALL PASSED ===')


if __name__ == '__main__':
    main()
