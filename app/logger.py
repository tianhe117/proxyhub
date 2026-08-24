"""File logger for ProxyHub (use via `app.utils`).

Single public interface: `log` (a stdlib logging.Logger), re-exported from
app.utils:

    from app.utils import log
    log.info('node switched')
    log.error('pull failed')

Import it through app.utils (`from app.utils import log`) rather than this
module directly. Writes one file per process start to config.LOGS_DIR,
named YYYY-MM-DD_HHMMSS.log (per design.md). Each line records time, level,
caller function name (接口名称), and message.
"""

import logging
import os
from datetime import datetime

from app import config


log = logging.getLogger('proxyhub')


def init_logger():
    """Configure the process-wide file logger after runtime paths are set."""
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    filename = datetime.now().strftime('%Y-%m-%d_%H%M%S') + '.log'
    path = os.path.join(config.LOGS_DIR, filename)

    target_dir = os.path.abspath(config.LOGS_DIR)
    for existing in list(log.handlers):
        if isinstance(existing, logging.FileHandler):
            existing_dir = os.path.dirname(os.path.abspath(existing.baseFilename))
            if existing_dir != target_dir:
                log.removeHandler(existing)
                existing.close()

    if not log.handlers:
        handler = logging.FileHandler(path, encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(funcName)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        ))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log
