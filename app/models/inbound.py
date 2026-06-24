"""Inbound CRUD operations."""

import json
from .database import get_db


def list_all():
    """Return all inbounds ordered by id."""
    db = get_db()
    return db.execute('SELECT * FROM inbounds ORDER BY id').fetchall()


def get_by_id(in_id):
    """Return an inbound by id, or None."""
    db = get_db()
    return db.execute('SELECT * FROM inbounds WHERE id = ?', (in_id,)).fetchone()


def create(name, protocol, listen_addr, port, params_json=None):
    """Insert an inbound and return its id."""
    if params_json is None:
        params_json = {}
    if isinstance(params_json, dict):
        params_json = json.dumps(params_json)
    db = get_db()
    cur = db.execute(
        '''INSERT INTO inbounds (name, protocol, listen_addr, port, params_json)
           VALUES (?, ?, ?, ?, ?)''',
        (name, protocol, listen_addr, int(port), params_json)
    )
    db.commit()
    return cur.lastrowid


def update(in_id, **fields):
    """Update mutable fields on an inbound."""
    allowed = {'name', 'protocol', 'listen_addr', 'port', 'params_json'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if 'params_json' in updates and isinstance(updates['params_json'], dict):
        updates['params_json'] = json.dumps(updates['params_json'])
    if not updates:
        return
    sets = ', '.join(f'{k} = ?' for k in updates)
    vals = list(updates.values()) + [in_id]
    db = get_db()
    db.execute(f'UPDATE inbounds SET {sets} WHERE id = ?', vals)
    db.commit()


def delete(in_id):
    """Delete an inbound."""
    db = get_db()
    db.execute('DELETE FROM inbounds WHERE id = ?', (in_id,))
    db.commit()
