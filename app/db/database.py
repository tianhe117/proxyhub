"""SQLite connection management and table initialisation (§3.1)."""

import sqlite3
import os
import threading

from app.settings import DB_PATH

_local = threading.local()

# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def get_db():
    """Return a thread-local SQLite connection with row_factory set."""
    if not hasattr(_local, 'db') or _local.db is None:
        db_path = DB_PATH
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
    """Create tables (idempotent) and seed sentinel rows."""
    db = get_db()
    _create_tables(db)
    _seed_sentinels(db)


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
            sub_id        INTEGER NOT NULL DEFAULT 0 REFERENCES subscriptions(id) ON DELETE CASCADE,
            name          TEXT NOT NULL,
            protocol      TEXT NOT NULL,
            address       TEXT NOT NULL,
            port          INTEGER NOT NULL,
            config_json   TEXT NOT NULL
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
            outbound_id INTEGER NOT NULL REFERENCES outbounds(id) ON DELETE CASCADE,
            node_id     INTEGER NOT NULL REFERENCES nodes(id)     ON DELETE CASCADE,
            priority    INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS outbound_fallback (
            outbound_id INTEGER PRIMARY KEY REFERENCES outbounds(id) ON DELETE CASCADE,
            node_id     INTEGER NOT NULL        REFERENCES nodes(id)     ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS services (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            inbound_id  INTEGER NOT NULL REFERENCES inbounds(id)  ON DELETE RESTRICT,
            outbound_id INTEGER NOT NULL REFERENCES outbounds(id) ON DELETE RESTRICT,
            auto_start  INTEGER DEFAULT 0
        );
    ''')


def _seed_sentinels(db):
    """Insert id=0 sentinel rows (custom subscription / direct outbound).

    These are placeholder parents so FOREIGN KEY constraints cover the
    sentinel values (nodes.sub_id=0, services.outbound_id=0).  They are
    included in list_all(); delete() guards id=0 so they stay read-only.
    """
    db.execute(
        "INSERT OR IGNORE INTO subscriptions (id, name, url) VALUES (0, 'custom', '')"
    )
    db.execute("INSERT OR IGNORE INTO outbounds (id, name) VALUES (0, 'direct')")
    db.commit()
