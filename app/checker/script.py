"""Subprocess wrapper for scripts/test.sh (§16).

Encapsulates calling the bash test script and parsing its JSON output.
"""

import json
import os
import subprocess


def _get_script_path():
    """Return the absolute path to scripts/test.sh."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, 'scripts', 'test.sh')


def tcp_ping(address, port, timeout, tag):
    """Run a TCP ping via test.sh.

    Args:
        address: IP/hostname
        port: int
        timeout: seconds
        tag: unique identifier for process cleanup

    Returns:
        dict: {success: bool, latency_ms?: int, error?: str}
    """
    script = _get_script_path()
    try:
        result = subprocess.run(
            ['bash', script, 'tcp_ping', str(address), str(port),
             str(timeout), tag],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        out = (result.stdout or '').strip()
        if out:
            return json.loads(out)
        return {'success': False, 'error': result.stderr or 'No output'}
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': 'TCP ping timed out'}
    except json.JSONDecodeError:
        return {'success': False, 'error': 'Invalid JSON response from test.sh'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def url_test(config_path, bin_type, bin_path, local_port, test_url, curl_timeout, tag):
    """Run a URL reachability test via test.sh.

    Args:
        config_path: absolute path to temp config JSON
        bin_type: 'xray' | 'sslocal' | 'sing-box'
        bin_path: absolute path to the binary
        local_port: SOCKS5 listen port (must match config)
        test_url: URL to curl through the proxy
        curl_timeout: seconds
        tag: unique identifier for process cleanup

    Returns:
        dict: {success: bool, latency_ms?: int, http_code?: int, error?: str}
    """
    script = _get_script_path()
    stdin_data = json.dumps({
        'config_path':  config_path,
        'bin_type':     bin_type,
        'bin_path':     bin_path,
        'local_port':   local_port,
        'test_url':     test_url,
        'curl_timeout': curl_timeout,
        'tag':          tag,
    })

    try:
        result = subprocess.run(
            ['bash', script, 'url_test'],
            input=stdin_data, capture_output=True, text=True,
            timeout=curl_timeout + 30,
        )
        out = (result.stdout or '').strip()
        if out:
            return json.loads(out)
        return {'success': False, 'error': result.stderr or 'No output'}
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': 'URL test timed out'}
    except json.JSONDecodeError:
        return {'success': False, 'error': 'Invalid JSON response from test.sh'}
    except Exception as e:
        return {'success': False, 'error': str(e)}
