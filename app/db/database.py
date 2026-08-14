"""SQLite connection management and table initialisation (§3.1)."""

import sqlite3
import os
import threading

from app.settings import get_db_path

_local = threading.local()

# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def get_db():
    """Return a thread-local SQLite connection with row_factory set."""
    if not hasattr(_local, 'db') or _local.db is None:
        db_path = get_db_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        _local.db = sqlite3.connect(db_path)
        _local.db.row_factory = sqlite3.Row
        _local.db.execute("PRAGMA journal_mode=WAL")
        _local.db.execute("PRAGMA foreign_keys=ON")
    return _local.db


def close_db():
    """Close the thread-local connection if it is open.

    Checkpoints WAL before closing so that -wal/-shm files are cleaned up.
    """
    db = getattr(_local, 'db', None)
    if db is not None:
        try:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        db.close()
        _local.db = None


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db():
    """Create tables (idempotent)."""
    db = get_db()
    _create_tables(db)


def _create_tables(db):
    """Create all tables (§3.1)."""
    db.executescript('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT NOT NULL,
            url              TEXT NOT NULL,
            filter_keywords  TEXT DEFAULT '',
            exclude_keywords TEXT DEFAULT '',
            updated_at       TEXT,
            upload_bytes     INTEGER DEFAULT 0,
            download_bytes   INTEGER DEFAULT 0,
            total_bytes      INTEGER DEFAULT 0,
            expire_at        INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS nodes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            sub_id        INTEGER DEFAULT 0,
            name          TEXT NOT NULL,
            protocol      TEXT NOT NULL,
            address       TEXT NOT NULL,
            port          INTEGER NOT NULL,
            config_json   TEXT NOT NULL,
            bin_type      TEXT DEFAULT 'xray'
        );

        CREATE TABLE IF NOT EXISTS inbounds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            protocol    TEXT NOT NULL,
            listen_addr TEXT DEFAULT '0.0.0.0',
            port        INTEGER NOT NULL,
            params_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS outbounds (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS outbound_nodes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            outbound_id INTEGER NOT NULL,
            node_id     INTEGER NOT NULL,
            priority    INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS services (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            inbound_id  INTEGER NOT NULL,
            outbound_id INTEGER NOT NULL,
            auto_start  INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        );
    ''')
