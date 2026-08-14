"""Service CRUD operations.

Service dict structure (sqlite3.Row → dict):
    id          int    primary key
    name        str    display name (also the config dir name)
    inbound_id  int    inbound listener id
    outbound_id int    outbound id
    auto_start  int    1 = start on app boot
    created_at  str    ISO timestamp (SQLite default)

Runtime state (running/stopped) is not persisted — it is derived live from
processes via app.process.manager.
"""

from .database import get_db


def list_all():
    """Return all services ordered by id."""
    db = get_db()
    return db.execute('SELECT * FROM services ORDER BY id').fetchall()


def get_by_id(svc_id):
    """Return a service by id, or None."""
    db = get_db()
    return db.execute('SELECT * FROM services WHERE id = ?', (svc_id,)).fetchone()


def create(name, inbound_id, outbound_id, auto_start=0):
    """Insert a service and return its id."""
    db = get_db()
    cur = db.execute(
        '''INSERT INTO services (name, inbound_id, outbound_id, auto_start)
           VALUES (?, ?, ?, ?)''',
        (name, inbound_id, outbound_id, auto_start)
    )
    db.commit()
    return cur.lastrowid


def update(svc_id, **fields):
    """Update mutable fields on a service."""
    allowed = {'name', 'inbound_id', 'outbound_id', 'auto_start'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    sets = ', '.join(f'{k} = ?' for k in updates)
    vals = list(updates.values()) + [svc_id]
    db = get_db()
    db.execute(f'UPDATE services SET {sets} WHERE id = ?', vals)
    db.commit()


def delete(svc_id):
    """Delete a service."""
    db = get_db()
    db.execute('DELETE FROM services WHERE id = ?', (svc_id,))
    db.commit()


def get_auto_start_services():
    """Return all services that have auto_start=1."""
    db = get_db()
    return db.execute(
        'SELECT * FROM services WHERE auto_start = 1'
    ).fetchall()
