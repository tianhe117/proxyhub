"""Low-level checker primitives — pure stdlib, zero project dependencies.

tcp_check(address, port, timeout=3)         → CheckResult
url_check(config, type, bin, port, url, timeout, tag) → CheckResult
"""

import json
import os
import socket
import subprocess
import time

from app.settings import BASE_DIR
from app.utils import CheckResult

_SCRIPTS_DIR = os.path.join(BASE_DIR, 'scripts')


# ============================================================================
# TCP check  (pure Python, zero subprocess)
# ============================================================================

def tcp_check(address: str, port: int, timeout: int = 3) -> CheckResult:
    try:
        t0 = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((address, int(port)))
        lat = round((time.time() - t0) * 1000)
        sock.close()
        return CheckResult(success=True, url_latency_ms=-1, tcp_latency_ms=lat,
                   http_code='0', error='')
    except Exception as e:
        return CheckResult(success=False, url_latency_ms=-1, tcp_latency_ms=-1,
                   http_code='0', error=str(e))


# ============================================================================
# URL check  (subprocess → proxy_url_check.sh)
# ============================================================================


def url_check(config_path: str, bin_type: str, bin_path: str,
              port: int, test_url: str, timeout: int, tag: str) -> CheckResult:
    """Run proxy_url_check.sh and parse its JSON output.

    Args match the shell script exactly:
        proxy_url_check.sh <config> <type> <bin> <port> <url> <timeout> <tag>
    """
    script = os.path.join(_SCRIPTS_DIR, 'proxy_url_check.sh')
    try:
        result = subprocess.run(
            ['bash', script, config_path, bin_type, bin_path,
             str(port), test_url, str(timeout), tag],
            capture_output=True, text=True, timeout=timeout + 30,
        )
        out = (result.stdout or '').strip()
        if out:
            data = json.loads(out)
            return CheckResult(
                success=(result.returncode == 0),
                url_latency_ms=data.get('latency_ms', -1),
                tcp_latency_ms=-1,
                http_code=data.get('http_code', '0'),
                error=data.get('error', ''),
            )
        return CheckResult(success=False, url_latency_ms=-1, tcp_latency_ms=-1,
                   http_code='0', error=result.stderr or 'No output')
    except subprocess.TimeoutExpired:
        return CheckResult(success=False, url_latency_ms=-1, tcp_latency_ms=-1,
                   http_code='0', error='URL check timed out')
    except json.JSONDecodeError:
        return CheckResult(success=False, url_latency_ms=-1, tcp_latency_ms=-1,
                   http_code='0', error='Invalid JSON from proxy_url_check.sh')
