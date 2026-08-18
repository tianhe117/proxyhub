"""sing-box package: config generation + process management + clash_api client.

Public interface — use `from app.singbox import ...`:

    config  : build_config, write_config
    process : start, stop, restart, is_running, get_version
    upgrade : check_upgrade, download_upgrade
"""

from app.singbox.config import build_config, write_config
from app.singbox.process import start, stop, restart, is_running, get_version
from app.singbox.upgrade import check_upgrade, download_upgrade

__all__ = [
    'build_config', 'write_config',
    'start', 'stop', 'restart', 'is_running', 'get_version',
    'check_upgrade', 'download_upgrade',
]
