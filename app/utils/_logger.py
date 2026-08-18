"""Internal file logger for ProxyHub (private — import via `app.utils` only).

Single public interface: `log` (a stdlib logging.Logger), re-exported from
app.utils:

    from app.utils import log
    log.info('node switched')
    log.error('pull failed')

This module is private (_logger.py); do not import it directly. Writes one
file per process start to settings.get_logs_dir(), named
YYYY-MM-DD_HHMMSS.log (per design.md). Each line records time, level,
caller function name (接口名称), and message.
"""

import logging
import os
from datetime import datetime

from app import settings


def _build_log():
    """Configure and return the process-wide logger (called once at import)."""
    os.makedirs(settings.get_logs_dir(), exist_ok=True)
    filename = datetime.now().strftime('%Y-%m-%d_%H%M%S') + '.log'
    path = os.path.join(settings.get_logs_dir(), filename)

    logger = logging.getLogger('proxyhub')
    if not logger.handlers:  # 防重：reload 时避免重复加 handler
        handler = logging.FileHandler(path, encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(funcName)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False  # 只落文件，不回传 root（避免 console/stderr 输出）
    return logger


log = _build_log()
