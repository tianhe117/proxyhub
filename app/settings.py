"""Configuration constants and default values for ProxyHub.

Settings are persisted to data/setting.json (auto-created from DEFAULT_SETTINGS
if missing).  Loaded once at module init into _store; reads hit memory,
writes update memory then persist to disk.
"""

import json
import os

# ---------------------------------------------------------------------------
# Default settings
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    'bin_path_xray':         './bin/xray',
    'bin_path_sslocal':      './bin/sslocal',
    'bin_path_singbox':      './bin/sing-box',
    'config_dir':            './config',
    'check_interval_normal': '240',
    'check_interval_failover': '30',
    'tcp_timeout':           '3',
    'curl_timeout':          '5',
    'test_url':              'https://www.gstatic.com/generate_204',
    'web_port':              '8080',
    'web_username':          'admin',
    'web_password':          '',
}

# ---------------------------------------------------------------------------
# Binary registry
# ---------------------------------------------------------------------------
BIN_REGISTRY = {
    'xray': {
        'exe': 'xray',
        'version_args': ['version'],
        'run_args': ['run', '-config', '{config}'],
    },
    'sslocal': {
        'exe': 'sslocal',
        'version_args': ['--version'],
        'run_args': ['-c', '{config}'],
    },
    'sing-box': {
        'exe': 'sing-box',
        'version_args': ['version'],
        'run_args': ['run', '-c', '{config}'],
    },
}

# ---------------------------------------------------------------------------
# GitHub repository configuration
# ---------------------------------------------------------------------------
BIN_REPOS = {
    'xray': {
        'repo': 'XTLS/Xray-core',
        'exe_names': ['xray'],
        'asset_patterns': {'linux-64': ['linux-64', 'linux-x64']},
    },
    'sslocal': {
        'repo': 'shadowsocks/shadowsocks-rust',
        'exe_names': ['sslocal'],
        'asset_patterns': {'linux-64': ['x86_64-unknown-linux']},
        'plugins': [{
            'name': 'obfs-local',
            'repo': 'shadowsocks/simple-obfs',
            'exe_names': ['obfs-local'],
            'asset_patterns': {'linux-64': ['obfs-local']},
        }],
    },
    'sing-box': {
        'repo': 'SagerNet/sing-box',
        'exe_names': ['sing-box'],
        'asset_patterns': {'linux-64': ['linux-amd64', 'linux-x64']},
    },
}

# ---------------------------------------------------------------------------
# Protocol → bin_type mapping
# ---------------------------------------------------------------------------
PROTOCOL_BIN_MAP = {
    'vmess':     'xray',
    'vless':     'xray',
    'trojan':    'xray',
    'ssr':       'xray',
    'anytls':    'xray',
    'hysteria':  'sing-box',
    'hysteria2': 'sing-box',
    'tuic':      'sing-box',
}

# ---------------------------------------------------------------------------
# Valid inbound protocols
# ---------------------------------------------------------------------------
VALID_INBOUND_PROTOCOLS = ('http', 'socks', 'ss', 'vmess')

# ---------------------------------------------------------------------------
# Valid bin_types per protocol (for frontend dropdown filtering)
# ---------------------------------------------------------------------------
VALID_BIN_TYPES = {
    'vmess':     ['xray'],
    'vless':     ['xray'],
    'trojan':    ['xray'],
    'ss':        ['xray', 'sslocal'],
    'ssr':       ['xray'],
    'hysteria2': ['sing-box'],
    'tuic':      ['sing-box'],
}

# ---------------------------------------------------------------------------
# SOCKS5 intermediate port range
# ---------------------------------------------------------------------------
SOCKS_PORT_START = 50000
SOCKS_PORT_END   = 60000

# ---------------------------------------------------------------------------
# Runtime path helpers
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_data_dir():
    return os.path.join(BASE_DIR, 'data')

def get_logs_dir():
    return os.path.join(BASE_DIR, 'logs')

def get_config_dir():
    return os.path.join(BASE_DIR, 'config')

def get_bin_dir():
    return os.path.join(BASE_DIR, 'bin')

def get_db_path():
    return os.path.join(get_data_dir(), 'proxyhub.db')

def get_pid_dir():
    return get_data_dir()


# ============================================================================
# Settings JSON — loaded once at init, reads hit memory, writes persist to disk
# ============================================================================

_SETTINGS_FILE = os.path.join(BASE_DIR, 'data', 'setting.json')


def _load_from_disk():
    """Read settings from disk, or create from defaults. Called once at init."""
    try:
        with open(_SETTINGS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = dict(DEFAULT_SETTINGS)
        _persist_to_disk(data)
        return data


def _persist_to_disk(data: dict):
    """Write settings to disk atomically."""
    os.makedirs(os.path.dirname(_SETTINGS_FILE), exist_ok=True)
    tmp = _SETTINGS_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, _SETTINGS_FILE)


# Load once at import time
_store = _load_from_disk()


# ---- public API ----

def get_setting(key):
    """Return a single setting value, or default if key not present."""
    if key in _store:
        return _store[key]
    return DEFAULT_SETTINGS.get(key)


def set_setting(key, value):
    """Insert or update a single setting (memory + disk)."""
    _store[key] = str(value)
    _persist_to_disk(_store)


def get_all_settings():
    """Return all settings as a dict {key: value}."""
    return dict(_store)


def update_settings(updates):
    """Apply a dict of {key: value} updates (memory + disk)."""
    for key, value in updates.items():
        _store[key] = str(value)
    _persist_to_disk(_store)


def reset_to_defaults():
    """Replace all settings with DEFAULT_SETTINGS (memory + disk)."""
    _store.clear()
    _store.update(DEFAULT_SETTINGS)
    _persist_to_disk(_store)
