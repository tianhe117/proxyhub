"""sing-box single resident process management: start / stop / restart.

No hot reload: restart() = stop + start. No PID file — the resident process
is identified by scanning system processes (Docker-native, matching the config
path in args) plus an in-memory pid from the last start().
"""

import os
import signal
import subprocess
import time

from app.settings import (
    CONFIG_PATH,
    SINGBOX_BIN_PATH,
    SINGBOX_RUN_ARGS,
)
from app.utils import log

# In-memory pid of the resident process (not persisted; design.md §4: no
# state carried across restarts).
_pid = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_running(pid):
    """Check if a process is alive — not zombie and not dead.

    Reads /proc/{pid}/stat for the real state; os.kill(pid, 0) alone returns
    True for zombie processes.
    """
    if pid is None:
        return False
    try:
        with open(f'/proc/{pid}/stat', 'r') as f:
            line = f.read()
            idx = line.rfind(')')
            if idx == -1 or idx + 2 >= len(line):
                return False
            state = line[idx + 2]
            return state not in ('Z', 'X')
    except (FileNotFoundError, OSError):
        return False


def _find_pid():
    """Return the resident sing-box pid, or None.

    Prefers the in-memory pid; falls back to scanning `ps` for a `sing-box`
    process whose args contain the generated config path.
    """
    global _pid
    if _pid and _is_running(_pid):
        return _pid

    config_name = os.path.basename(CONFIG_PATH)
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
            if pid == os.getpid():
                continue
            if 'Z' in stat:
                continue  # skip zombies
            if comm == os.path.basename(SINGBOX_BIN_PATH) and config_name in args:
                return pid
    except Exception as e:
        log.error(f'Failed to scan processes: {e}')
    return None


def _kill_pid(pid, timeout=3):
    """Kill a process group: SIGTERM -> poll -> SIGKILL.

    Returns True if the process is dead (or already was).
    """
    if not _is_running(pid):
        return True

    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        return True

    for _ in range(int(timeout / 0.3)):
        if not _is_running(pid):
            return True
        time.sleep(0.3)

    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGKILL)
        time.sleep(0.1)
    except (OSError, ProcessLookupError):
        pass

    return not _is_running(pid)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_running() -> bool:
    """Return True if the resident sing-box process is alive."""
    return _find_pid() is not None


def start() -> int:
    """Start the resident sing-box process and return its pid (idempotent).

    Raises:
        RuntimeError: binary missing, or process exited immediately.
    """
    global _pid
    pid = _find_pid()
    if pid:
        _pid = pid
        log.info(f'sing-box already running (PID {pid})')
        return pid

    bin_path = SINGBOX_BIN_PATH
    if not bin_path or not os.path.isfile(bin_path):
        raise RuntimeError(f'Binary not found: {bin_path}')

    run_args = [a.format(config=CONFIG_PATH)
                for a in SINGBOX_RUN_ARGS]
    cmd = [bin_path] + run_args
    log.info(f'Starting sing-box: {" ".join(cmd)}')

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,  # new session, so we can kill the whole group
    )

    time.sleep(0.2)
    if proc.poll() is not None:
        raise RuntimeError(f'sing-box exited immediately with code {proc.returncode}')

    _pid = proc.pid
    log.info(f'sing-box started (PID {proc.pid})')
    return proc.pid


def stop() -> dict:
    """Stop the resident sing-box process.

    Returns:
        dict: {success, message, killed}
    """
    global _pid
    pid = _find_pid()
    if pid is None:
        _pid = None
        log.info('sing-box: no running process found')
        return {'success': True, 'message': 'No process running', 'killed': 0}

    if _kill_pid(pid):
        _pid = None
        log.info(f'sing-box stopped (PID {pid})')
        return {'success': True, 'message': 'Stopped', 'killed': 1}

    log.error(f'sing-box failed to stop (PID {pid})')
    return {'success': False, 'message': f'Failed to kill PID {pid}', 'killed': 0}


def restart() -> dict:
    """Stop then start the resident process.

    Returns:
        dict: {success, message}
    """
    stop()
    time.sleep(0.5)  # let the port release before re-binding
    try:
        pid = start()
        return {'success': True, 'message': f'Restarted (PID {pid})'}
    except Exception as e:
        return {'success': False, 'message': str(e)}
