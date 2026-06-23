"""Process lifecycle management (§8.3).

Manages subprocess.Popen instances for proxy binaries.
PID files: data/{service_name}_{bin_type}.pid
"""

import os
import signal
import subprocess
import time

from app.settings import BIN_REGISTRY, get_bin_dir, get_pid_dir
from app.models.setting import get_setting
from app.logger import log


def _get_pid_file(service_name, bin_type):
    """Return the absolute path to a PID file."""
    return os.path.join(get_pid_dir(), f'{service_name}_{bin_type}.pid')


def _read_pid(pid_file):
    """Read a PID from a file.  Return None if the file doesn't exist."""
    try:
        with open(pid_file, 'r') as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _write_pid(pid_file, pid):
    """Write a PID to a file."""
    os.makedirs(os.path.dirname(pid_file), exist_ok=True)
    with open(pid_file, 'w') as f:
        f.write(str(pid))


def _remove_pid(pid_file):
    """Remove a PID file if it exists."""
    try:
        os.remove(pid_file)
    except FileNotFoundError:
        pass


def _is_running(pid):
    """Check if a process with *pid* is alive (POSIX)."""
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _get_bin_path(bin_type):
    """Resolve binary path from settings."""
    key = f'bin_path_{bin_type if bin_type != "sing-box" else "singbox"}'
    path = get_setting(key) or ''
    if path and not os.path.isabs(path):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), path)
    return path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_process(service_name, bin_type, config_path, role=''):
    """Start a proxy binary process.

    Args:
        service_name: e.g. 'my-service'
        bin_type: 'xray' | 'sslocal' | 'sing-box'
        config_path: absolute path to the JSON config file
        role: optional suffix for PID file, e.g. 'in' or 'out'

    Returns:
        PID of the launched process.
    """
    pid_key = f'{bin_type}_{role}' if role else bin_type
    pid_file = _get_pid_file(service_name, pid_key)

    # Check if already running
    existing_pid = _read_pid(pid_file)
    if _is_running(existing_pid):
        log('warn', 'process', f'{service_name}/{bin_type} already running (PID {existing_pid})')
        return existing_pid

    bin_path = _get_bin_path(bin_type)
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

    _write_pid(pid_file, proc.pid)
    log('ok', bin_type, f'{service_name}/{bin_type} started (PID {proc.pid})')
    return proc.pid


def stop_process(service_name, bin_type):
    """Stop a proxy binary process.

    Graceful: SIGTERM → wait up to 3s → SIGKILL.
    """
    pid_file = _get_pid_file(service_name, bin_type)
    pid = _read_pid(pid_file)

    if pid is None:
        log('info', 'process', f'{service_name}/{bin_type} not running (no PID file)')
        _remove_pid(pid_file)
        return

    if not _is_running(pid):
        log('info', 'process', f'{service_name}/{bin_type} already stopped')
        _remove_pid(pid_file)
        return

    # SIGTERM
    log('info', bin_type, f'Stopping {service_name}/{bin_type} (PID {pid})')
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        _remove_pid(pid_file)
        return

    # Wait up to 3s
    for _ in range(10):
        if not _is_running(pid):
            log('ok', bin_type, f'{service_name}/{bin_type} stopped')
            _remove_pid(pid_file)
            return
        time.sleep(0.3)

    # SIGKILL
    log('warn', 'process', f'Force-killing {service_name}/{bin_type}')
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    _remove_pid(pid_file)


def stop_all_for_service(service_name):
    """Stop all binaries associated with a service."""
    pid_dir = get_pid_dir()
    prefix = f'{service_name}_'
    if os.path.isdir(pid_dir):
        for fname in os.listdir(pid_dir):
            if fname.startswith(prefix) and fname.endswith('.pid'):
                key = fname[len(prefix):-4]  # e.g. 'xray_in', 'xray_out'
                stop_process(service_name, key)


def stop_all_processes():
    """Stop all running proxy processes by matching bin names."""
    from app.settings import get_bin_dir
    bin_dir = os.path.abspath(get_bin_dir())
    bin_names = set()
    kill_set = set()
    if os.path.isdir(bin_dir):
        for fname in os.listdir(bin_dir):
            fpath = os.path.join(bin_dir, fname)
            if os.path.isfile(fpath) and os.access(fpath, os.X_OK):
                bin_names.add(fname)
                kill_set.add(fpath)

    count = 0
    for proc in os.popen('ps -eo pid,comm,args').readlines():
        parts = proc.strip().split(None, 2)
        if len(parts) < 3:
            continue
        pid_str, comm, args = parts
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        # Match by command name or full path in args
        matched = comm in bin_names
        if not matched:
            for k in kill_set:
                if k in args:
                    matched = True
                    break
        if matched and pid != os.getpid():
            try:
                os.kill(pid, signal.SIGTERM)
                count += 1
            except (OSError, ProcessLookupError):
                pass

    # Clean up all PID files
    pid_dir = get_pid_dir()
    if os.path.isdir(pid_dir):
        for fname in os.listdir(pid_dir):
            if fname.endswith('.pid'):
                _remove_pid(os.path.join(pid_dir, fname))

    return count


def get_process_status(service_name, bin_type):
    """Return 'running' or 'stopped' for a specific process."""
    pid_file = _get_pid_file(service_name, bin_type)
    pid = _read_pid(pid_file)
    return 'running' if _is_running(pid) else 'stopped'


def get_process_uptime(service_name, bin_type):
    """Return uptime in seconds, or None if not running."""
    pid_file = _get_pid_file(service_name, bin_type)
    pid = _read_pid(pid_file)
    if not _is_running(pid):
        return None
    try:
        stat = os.stat(f'/proc/{pid}')
        return int(time.time() - stat.st_ctime)
    except (FileNotFoundError, OSError):
        return None


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
        # Return first non-empty line
        for line in output.splitlines():
            line = line.strip()
            if line:
                return line
        return 'N/A'
    except Exception:
        return 'N/A'
