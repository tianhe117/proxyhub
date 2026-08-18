"""sing-box package: config generation + process management + clash_api client.

Public interface — use `from app.singbox import ...`:

    protocol : build_outbound, build_inbound
    config   : build_config, write_config
    process  : start, stop, restart, is_running
    upgrade  : get_version, check_upgrade, download_upgrade
"""

from app.singbox.protocol import build_outbound, build_inbound
from app.singbox.config import build_config, write_config
from app.singbox.process import start, stop, restart, is_running
from app.singbox.upgrade import get_version, check_upgrade, download_upgrade

__all__ = [
    'build_outbound', 'build_inbound',
    'build_config', 'write_config',
    'start', 'stop', 'restart', 'is_running',
    'get_version', 'check_upgrade', 'download_upgrade',
]
