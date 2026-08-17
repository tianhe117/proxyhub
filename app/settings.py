"""Configuration constants and defaults for ProxyHub v2.

Settings persist to data/setting.json (auto-created from DEFAULT_SETTINGS if
missing). Loaded once at module init into _store; reads hit memory, writes
update memory then persist to disk.

v2 uses a single engine: sing-box. Multi-engine fields are dropped
(BIN_REGISTRY, BIN_REPOS, per-protocol bin map, SOCKS/TEST port pools).
Paths are not hard-coded: resolved from BASE_DIR (override with the
PROXYHUB_HOME env var, e.g. Docker volume mounts / venv repo root).
"""

import json
import os

# ---------------------------------------------------------------------------
# Default settings
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    'bin_path_singbox':        './data/bin/sing-box',
    'check_interval_normal':   '240',
    'check_interval_failover': '30',
    'tcp_timeout':             '3',
    'curl_timeout':            '5',
    'test_url':                'https://www.gstatic.com/generate_204',
    'web_port':                '8080',
    'web_username':            'admin',
    'web_password':            '',
}

# ---------------------------------------------------------------------------
# sing-box binary constants (single engine)
# ---------------------------------------------------------------------------
SINGBOX_EXE = 'sing-box'
SINGBOX_VERSION_ARGS = ['version']
SINGBOX_RUN_ARGS = ['run', '-c', '{config}']

# ---------------------------------------------------------------------------
# GitHub release info (upgrade service downloads sing-box only)
# ---------------------------------------------------------------------------
SINGBOX_REPO = 'SagerNet/sing-box'
SINGBOX_ASSET_PATTERNS = {'linux-64': ['linux-amd64', 'linux-x64']}

# ---------------------------------------------------------------------------
# Supported protocols — sing-box covers all of these (no per-bin mapping)
# ---------------------------------------------------------------------------
SUPPORTED_PROTOCOLS = ('vmess', 'vless', 'trojan', 'ss', 'hysteria2', 'tuic', 'direct')

# ---------------------------------------------------------------------------
# Valid inbound protocols
# ---------------------------------------------------------------------------
VALID_INBOUND_PROTOCOLS = ('http', 'socks', 'ss', 'vmess')

# ---------------------------------------------------------------------------
# Runtime path helpers — resolved from BASE_DIR (PROXYHUB_HOME override)
# ---------------------------------------------------------------------------
BASE_DIR = os.environ.get('PROXYHUB_HOME') or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))


def get_data_dir():
    return os.path.join(BASE_DIR, 'data')


def get_logs_dir():
    return os.path.join(BASE_DIR, 'logs')


def get_bin_dir():
    return os.path.join(get_data_dir(), 'bin')


def get_config_path():
    return os.path.join(get_data_dir(), 'config.json')


def get_settings_path():
    return os.path.join(get_data_dir(), 'setting.json')


def get_db_path():
    return os.path.join(get_data_dir(), 'proxyhub.db')


def get_pid_dir():
    return get_data_dir()


def get_singbox_bin_path():
    """Return the sing-box binary path (from settings, default data/bin/sing-box)."""
    return get_setting('bin_path_singbox')


# ============================================================================
# Settings JSON — loaded once at init, reads hit memory, writes persist to disk
# ============================================================================

_SETTINGS_FILE = get_settings_path()


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
