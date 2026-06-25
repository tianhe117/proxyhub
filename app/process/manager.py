"""Process lifecycle management.

Docker-native approach: scan system processes directly, no PID files.
Identifies processes by matching config/{service_name}/ paths in args.
"""

import os
import re
import signal
import subprocess
import time

from app.settings import BIN_REGISTRY, get_bin_dir
from app.models.setting import get_setting
from app.logger import log


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_running(pid):
    """Check if a process is alive — not zombie and not dead.

    Reads /proc/{pid}/stat to get the real process state.
    os.kill(pid, 0) alone returns True for zombie processes.
    """
    if pid is None:
        return False
    try:
        with open(f'/proc/{pid}/stat', 'r') as f:
            line = f.read()
            # Format: "12345 (comm) S ..." — state is right after the closing ')'
            idx = line.rfind(')')
            if idx == -1 or idx + 2 >= len(line):
                return False
            state = line[idx + 2]
            return state not in ('Z', 'X')
    except (FileNotFoundError, OSError):
        return False


def _get_bin_path(bin_type):
    """Resolve binary path from settings."""
    key = f'bin_path_{bin_type if bin_type != "sing-box" else "singbox"}'
    path = get_setting(key) or ''
    if path and not os.path.isabs(path):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), path)
    return path


def _get_bin_names():
    """Get set of executable names from bin directory."""
    bin_dir = os.path.abspath(get_bin_dir())
    names = set()
    if os.path.isdir(bin_dir):
        for fname in os.listdir(bin_dir):
            fpath = os.path.join(bin_dir, fname)
            if os.path.isfile(fpath) and os.access(fpath, os.X_OK):
                names.add(fname)
    return names


def _scan_processes():
    """Scan system processes, yield (pid, comm, args).

    Skips zombie (defunct) processes — they are dead but not yet reaped.
    """
    try:
        result = subprocess.run(
            ['ps', '-eo', 'pid,stat,comm,args'],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines()[1:]:  # skip header
            parts = line.strip().split(None, 3)
            if len(parts) < 4:
                continue
            try:
                pid = int(parts[0])
                stat = parts[1]
                comm = parts[2]
                args = parts[3]
            except (ValueError, IndexError):
                continue
            # Skip zombie processes (state contains 'Z')
            if 'Z' in stat:
                continue
            yield pid, comm, args
    except Exception as e:
        log('error', 'process', f'Failed to scan processes: {e}')


def _extract_service_info(args):
    """Extract service name and role from config path in args.

    Matches: config/{service_name}/{type}_{role}.json
    Returns: (service_name, role_key) or None

    Example:
        args = '/opt/proxyhub/./bin/xray run -config /opt/proxyhub/config/my-service/xray_out.json'
        Returns: ('my-service', 'xray_out')
    """
    match = re.search(r'config/([^/]+)/((?:xray|sslocal|sing-box)_(?:in|out))\.json', args)
    if match:
        return match.group(1), match.group(2)
    return None


def _kill_pid(pid, timeout=3):
    """Kill a process group: SIGTERM → wait → SIGKILL.

    Returns True if process was killed or already dead.
    """
    if not _is_running(pid):
        return True

    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        return True

    # Wait for graceful shutdown
    for _ in range(int(timeout / 0.3)):
        if not _is_running(pid):
            return True
        time.sleep(0.3)

    # Force kill
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGKILL)
        time.sleep(0.1)
    except (OSError, ProcessLookupError):
        pass

    return not _is_running(pid)


# ---------------------------------------------------------------------------
# Public API — Process queries
# ---------------------------------------------------------------------------

def get_service_processes(service_name):
    """Get all processes belonging to a service.

    Returns:
        dict: {role_key: {'pid': int, 'comm': str, 'args': str}}
        Example: {'xray_in': {'pid': 123, 'comm': 'xray', 'args': '...'}}
    """
    result = {}
    config_prefix = f'config/{service_name}/'

    for pid, comm, args in _scan_processes():
        if pid == os.getpid():
            continue
        if config_prefix in args:
            info = _extract_service_info(args)
            if info:
                _, role_key = info
                result[role_key] = {
                    'pid': pid,
                    'comm': comm,
                    'args': args,
                }

    return result


def get_all_processes():
    """Get all system processes (belonging to any service).

    Returns:
        dict: {service_name: {role_key: {'pid': int, 'comm': str}}}
    """
    result = {}

    for pid, comm, args in _scan_processes():
        if pid == os.getpid():
            continue
        info = _extract_service_info(args)
        if info:
            service_name, role_key = info
            result.setdefault(service_name, {})[role_key] = {
                'pid': pid,
                'comm': comm,
            }

    return result


def is_service_running(service_name):
    """Check if a service is fully running (both in and out processes alive).

    Returns:
        bool: True if service has at least one 'in' and one 'out' process running.
    """
    procs = get_service_processes(service_name)
    has_in = any('_in' in k for k in procs)
    has_out = any('_out' in k for k in procs)
    return has_in and has_out


def count_processes():
    """Count running proxy processes (only those with config paths)."""
    all_procs = get_all_processes()
    return sum(len(procs) for procs in all_procs.values())


# ---------------------------------------------------------------------------
# Public API — Process control
# ---------------------------------------------------------------------------

def start_process(service_name, bin_type, config_path, role=''):
    """Start a proxy binary process.

    Args:
        service_name: e.g. 'my-service'
        bin_type: 'xray' | 'sslocal' | 'sing-box'
        config_path: absolute path to the JSON config file
        role: 'in' or 'out'

    Returns:
        PID of the launched process.

    Raises:
        RuntimeError: if process already running or failed to start.
    """
    # Check if already running
    existing = get_service_processes(service_name)
    role_key = f'{bin_type}_{role}' if role else bin_type
    if role_key in existing:
        pid = existing[role_key]['pid']
        log('warn', 'process', f'{service_name}/{role_key} already running (PID {pid})')
        return pid

    bin_path = _get_bin_path(bin_type)
    if not bin_path or not os.path.isfile(bin_path):
        raise RuntimeError(f'Binary not found: {bin_path}')

    registry = BIN_REGISTRY[bin_type]
    run_args = [arg.format(config=config_path) for arg in registry['run_args']]
    cmd = [bin_path] + run_args

    log('info', bin_type, f'Starting: {" ".join(cmd)}')

    # Ensure PATH includes the bin directory (needed for sslocal to find obfs-local)
    env = os.environ.copy()
    bin_dir = os.path.dirname(os.path.abspath(bin_path))
    env['PATH'] = f'{bin_dir}:{env.get("PATH", "")}'

    # Start in a new session (setsid equivalent)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        preexec_fn=os.setsid,
    )

    # Brief check that process started successfully
    time.sleep(0.2)
    if proc.poll() is not None:
        raise RuntimeError(f'Process exited immediately with code {proc.returncode}')

    log('ok', bin_type, f'{service_name}/{role_key} started (PID {proc.pid})')
    return proc.pid


def stop_service(service_name):
    """Stop all processes belonging to a service.

    Returns:
        dict: {success: bool, message: str, killed: int}
    """
    procs = get_service_processes(service_name)
    if not procs:
        log('info', 'process', f'{service_name}: no running processes found')
        return {'success': True, 'message': 'No processes running', 'killed': 0}

    log('info', 'process', f'Stopping {service_name}: found {len(procs)} processes')

    killed = 0
    failed = []
    for role_key, info in procs.items():
        pid = info['pid']
        log('info', 'process', f'  Killing {role_key} (PID {pid})')
        if _kill_pid(pid):
            killed += 1
        else:
            failed.append(f'{role_key} (PID {pid})')

    if failed:
        log('error', 'process', f'{service_name}: failed to kill: {failed}')
        return {'success': False, 'message': f'Failed to kill: {", ".join(failed)}', 'killed': killed}

    log('ok', 'process', f'{service_name}: stopped {killed} processes')
    return {'success': True, 'message': f'Stopped {killed} processes', 'killed': killed}


def stop_all_processes():
    """Stop ALL proxy processes by matching bin names (aggressive mode).

    For restart-all: kills everything matching bin/ executables,
    regardless of config path.

    Returns:
        int: Number of processes killed.
    """
    bin_names = _get_bin_names()
    if not bin_names:
        log('warn', 'process', 'No binaries found in bin directory')
        return 0

    log('info', 'process', f'Stopping ALL processes matching: {bin_names}')

    # Collect PIDs to kill
    pids_to_kill = set()
    for pid, comm, args in _scan_processes():
        if pid == os.getpid():
            continue
        # Match by comm name or bin path in args
        if comm in bin_names:
            pids_to_kill.add(pid)
            continue
        for name in bin_names:
            if name in args:
                pids_to_kill.add(pid)
                break

    if not pids_to_kill:
        log('info', 'process', 'No matching processes found')
        return 0

    log('info', 'process', f'Found {len(pids_to_kill)} processes to kill')

    # Kill all
    killed = 0
    for pid in pids_to_kill:
        if _kill_pid(pid, timeout=2):
            killed += 1

    # Verify
    time.sleep(0.2)
    survivors = []
    for pid in pids_to_kill:
        if _is_running(pid):
            survivors.append(pid)

    if survivors:
        log('warn', 'process', f'{len(survivors)} processes survived: {survivors}')
    else:
        log('ok', 'process', f'Successfully killed {killed} processes')

    return killed


# ---------------------------------------------------------------------------
# Public API — Utilities
# ---------------------------------------------------------------------------

def get_version(bin_type):
    """Return the version string for a binary, or 'N/A'."""
    bin_path = _get_bin_path(bin_type)
    if not os.path.isfile(bin_path):
        return 'N/A'
    registry = BIN_REGISTRY[bin_type]
    try:
        result = subprocess.run(
            [bin_path] + registry['version_args'],
            capture_output=True, text=True, timeout=5,
        )
        output = result.stdout or result.stderr or ''
        for line in output.splitlines():
            line = line.strip()
            if line:
                return line
        return 'N/A'
    except Exception:
        return 'N/A'
