"""Application-level constants and runtime paths.

Defaults preserve the current repository-local data/log layout.  The app
factory may supply explicit path overrides for isolated runs; environment
variable behavior is intentionally unchanged in this refactor.
"""

import os


SINGBOX_VERSION_ARGS = ['version']
SINGBOX_RUN_ARGS = ['run', '-c', '{config}']
SINGBOX_REPO = 'SagerNet/sing-box'
SINGBOX_ASSET_PATTERNS = {'linux-64': ['linux-amd64', 'linux-x64']}

SUPPORTED_PROTOCOLS = ('vmess', 'vless', 'trojan', 'ss', 'hysteria2', 'tuic', 'direct')
VALID_INBOUND_PROTOCOLS = ('http', 'socks', 'ss', 'vmess')

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH_KEYS = {
    'BASE_DIR', 'DATA_DIR', 'LOGS_DIR', 'CONFIG_PATH', 'SETTINGS_PATH',
    'DB_PATH', 'SINGBOX_BIN_DIR', 'SINGBOX_BIN_PATH',
}


def configure(overrides=None):
    """Reset runtime paths to defaults, then apply explicit overrides."""
    global BASE_DIR, DATA_DIR, LOGS_DIR, CONFIG_PATH, SETTINGS_PATH
    global DB_PATH, SINGBOX_BIN_DIR, SINGBOX_BIN_PATH

    values = dict(overrides or {})
    base_dir = os.path.abspath(values.get('BASE_DIR', _PROJECT_ROOT))
    data_dir = os.path.abspath(values.get('DATA_DIR', os.path.join(base_dir, 'data')))

    BASE_DIR = base_dir
    DATA_DIR = data_dir
    LOGS_DIR = os.path.abspath(values.get('LOGS_DIR', os.path.join(base_dir, 'logs')))
    CONFIG_PATH = os.path.abspath(values.get('CONFIG_PATH', os.path.join(data_dir, 'config.json')))
    SETTINGS_PATH = os.path.abspath(values.get('SETTINGS_PATH', os.path.join(data_dir, 'setting.json')))
    DB_PATH = os.path.abspath(values.get('DB_PATH', os.path.join(data_dir, 'proxyhub.db')))
    SINGBOX_BIN_DIR = os.path.abspath(
        values.get('SINGBOX_BIN_DIR', os.path.join(data_dir, 'bin'))
    )
    SINGBOX_BIN_PATH = os.path.abspath(
        values.get('SINGBOX_BIN_PATH', os.path.join(SINGBOX_BIN_DIR, 'sing-box'))
    )

    unknown = set(values) - _PATH_KEYS
    if unknown:
        raise KeyError(f'Unknown runtime config keys: {sorted(unknown)}')


configure()
