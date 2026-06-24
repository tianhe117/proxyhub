"""Service CRUD operations."""

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
    allowed = {'name', 'inbound_id', 'outbound_id', 'status', 'auto_start'}
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


def update_status(svc_id, status):
    """Update only the status field."""
    db = get_db()
    db.execute('UPDATE services SET status = ? WHERE id = ?', (status, svc_id))
    db.commit()


def get_auto_start_services():
    """Return all services that have auto_start=1."""
    db = get_db()
    return db.execute(
        'SELECT * FROM services WHERE auto_start = 1'
    ).fetchall()
