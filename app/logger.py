"""Web-accessible log collector (§17).

Captures all stdout/stderr output into an in-memory deque and exposes it
via `get_logs(since)` for the /api/logs endpoint.  Also persists every log
line to logs/YYYY-MM-DD_HHMMSS.log so logs survive restarts.
"""

import os
import sys
import threading
from datetime import datetime
from collections import deque

from app.settings import get_logs_dir


class WebLogger:
    """Thread-safe ring buffer that captures process and system output."""

    def __init__(self, maxlen=500):
        self.logs = deque(maxlen=maxlen)
        self.lock = threading.Lock()
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        self._writer = None
        self._log_file = None

    def install(self):
        """Replace sys.stdout / sys.stderr with a LogWriter that feeds us."""
        if self._writer is not None:
            return
        # Open persistent log file (append mode, line-buffered)
        log_dir = get_logs_dir()
        os.makedirs(log_dir, exist_ok=True)
        log_name = datetime.now().strftime('%Y-%m-%d_%H%M%S.log')
        self._log_file = open(os.path.join(log_dir, log_name), 'a', buffering=1)
        self._writer = LogWriter(self, sys.__stdout__, 'info')
        self._err_writer = LogWriter(self, sys.__stderr__, 'error')
        sys.stdout = self._writer
        sys.stderr = self._err_writer

    def restore(self):
        """Restore the original stdout/stderr streams."""
        if self._writer is None:
            return
        sys.stdout = self._stdout
        sys.stderr = self._stderr
        self._writer = None
        self._err_writer = None
        if self._log_file:
            self._log_file.close()
            self._log_file = None

    def add(self, level, module, message):
        """Push one log entry into the buffer and persist to file."""
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        msg = message.strip() if message else ''
        with self.lock:
            self.logs.append({
                'time':    ts[-8:],   # HH:MM:SS for frontend
                'level':   level,
                'module':  module,
                'message': msg,
            })
        # Persist to file (outside lock — file is line-buffered, OS handles interleaving)
        if self._log_file:
            self._log_file.write(f'[{ts}] [{level.upper()}] [{module}] {msg}\n')

    def get_logs(self, since=0):
        """Return log entries whose index >= *since*."""
        with self.lock:
            total = len(self.logs)
            if since >= total:
                return [], total
            return list(self.logs)[since:], total


class LogWriter:
    """File-like object that forwards writes to both the real stream and
    the WebLogger."""

    def __init__(self, weblogger, original, level):
        self._logger = weblogger
        self.original = original
        self._level = level

    def write(self, text):
        # Always forward to the real terminal / stream
        self.original.write(text)
        stripped = text.strip()
        if not stripped:
            return
        # Extract [module] prefix if present
        module = 'system'
        msg = stripped
        if stripped.startswith('['):
            end = stripped.find(']')
            if end != -1:
                module = stripped[1:end]
                msg = stripped[end + 1:].strip()
        self._logger.add(self._level, module, msg)

    def flush(self):
        self.original.flush()

    def fileno(self):
        return self.original.fileno()

    def __getattr__(self, name):
        return getattr(self.original, name)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
web_logger = WebLogger()


def log(level, module, message):
    """Convenience shortcut to add a log entry."""
    web_logger.add(level, module, message)
