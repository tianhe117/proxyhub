"""Settings CRUD operations."""

from .database import get_db
from app.settings import DEFAULT_SETTINGS


def get_all_settings():
    """Return all settings as a dict {key: value}."""
    db = get_db()
    rows = db.execute('SELECT key, value FROM settings').fetchall()
    return {row['key']: row['value'] for row in rows}


def get_setting(key):
    """Return a single setting value, or None if not found."""
    db = get_db()
    row = db.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    if row:
        return row['value']
    # Fall back to default if key exists there
    return DEFAULT_SETTINGS.get(key)


def set_setting(key, value):
    """Insert or update a single setting."""
    db = get_db()
    db.execute(
        'INSERT INTO settings (key, value) VALUES (?, ?) '
        'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
        (key, str(value))
    )
    db.commit()


def update_settings(updates):
    """Apply a dict of {key: value} updates."""
    for key, value in updates.items():
        set_setting(key, value)


def reset_to_defaults():
    """Replace all settings with DEFAULT_SETTINGS."""
    db = get_db()
    db.execute('DELETE FROM settings')
    for key, value in DEFAULT_SETTINGS.items():
        db.execute('INSERT INTO settings (key, value) VALUES (?, ?)',
                   (key, value))
    db.commit()
