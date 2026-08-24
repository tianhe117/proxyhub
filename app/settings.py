"""Persistent user settings for ProxyHub v2.

Settings persist to data/setting.json (auto-created from DEFAULT_SETTINGS if
missing). The store loads lazily; reads hit memory and writes update both
memory and disk.

Application constants and runtime paths live in :mod:`app.config`.
"""

import json
import os

from app import config

# ---------------------------------------------------------------------------
# Default settings
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    'check_interval_normal':   '240',
    'check_interval_failover': '30',
    'tcp_timeout':             '3',
    'curl_timeout':            '5',
    'test_url':                'https://www.gstatic.com/generate_204',
    'web_port':                '8080',
    'web_username':            'admin',
    'web_password':            '',
    'clash_api_port':          '9090',
}

# ============================================================================
# Settings JSON — loaded lazily, reads hit memory, writes persist to disk
# ============================================================================

def _load_from_disk():
    """Read settings from disk, or create from defaults. Called once at init."""
    try:
        with open(config.SETTINGS_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = dict(DEFAULT_SETTINGS)
        _persist_to_disk(data)
        return data


def _persist_to_disk(data: dict):
    """Write settings to disk atomically."""
    os.makedirs(os.path.dirname(config.SETTINGS_PATH), exist_ok=True)
    tmp = config.SETTINGS_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, config.SETTINGS_PATH)


_store = None


def configure():
    """Reset the lazy store after runtime path configuration changes."""
    global _store
    _store = None


def _get_store():
    global _store
    if _store is None:
        _store = _load_from_disk()
    return _store


# ---- public API ----

def get_setting(key):
    """Return a single setting value, or default if key not present.

    When falling back to the default, the value is also persisted to disk
    so that subsequent reads and the settings page reflect all known keys.
    """
    store = _get_store()
    if key in store:
        return store[key]
    default = DEFAULT_SETTINGS.get(key)
    if default is not None:
        store[key] = default
        _persist_to_disk(store)
    return default


def set_setting(key, value):
    """Insert or update a single setting (memory + disk)."""
    store = _get_store()
    store[key] = str(value)
    _persist_to_disk(store)


def get_all_settings():
    """Return all settings as a dict {key: value}."""
    return dict(_get_store())


def update_settings(updates):
    """Apply a dict of {key: value} updates (memory + disk)."""
    store = _get_store()
    for key, value in updates.items():
        store[key] = str(value)
    _persist_to_disk(store)


def reset_to_defaults():
    """Replace all settings with DEFAULT_SETTINGS (memory + disk)."""
    store = _get_store()
    store.clear()
    store.update(DEFAULT_SETTINGS)
    _persist_to_disk(store)
