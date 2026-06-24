"""Subscription CRUD operations."""

from .database import get_db


def list_all():
    """Return all subscriptions ordered by id."""
    db = get_db()
    return db.execute('SELECT * FROM subscriptions ORDER BY id').fetchall()


def get_by_id(sub_id):
    """Return a single subscription by id, or None."""
    db = get_db()
    return db.execute(
        'SELECT * FROM subscriptions WHERE id = ?', (sub_id,)
    ).fetchone()


def create(name, url, filter_keywords='', exclude_keywords=''):
    """Insert a new subscription and return its id."""
    db = get_db()
    cur = db.execute(
        'INSERT INTO subscriptions (name, url, filter_keywords, exclude_keywords) '
        'VALUES (?, ?, ?, ?)',
        (name, url, filter_keywords, exclude_keywords)
    )
    db.commit()
    return cur.lastrowid


def update(sub_id, **fields):
    """Update fields on a subscription.  Only supplied kwargs are changed."""
    allowed = {'name', 'url', 'filter_keywords', 'exclude_keywords',
               'updated_at', 'upload_bytes', 'download_bytes', 'total_bytes', 'expire_at'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    sets = ', '.join(f'{k} = ?' for k in updates)
    vals = list(updates.values()) + [sub_id]
    db = get_db()
    db.execute(f'UPDATE subscriptions SET {sets} WHERE id = ?', vals)
    db.commit()


def delete(sub_id):
    """Delete a subscription and its associated nodes."""
    db = get_db()
    db.execute('DELETE FROM nodes WHERE sub_id = ?', (sub_id,))
    db.execute('DELETE FROM subscriptions WHERE id = ?', (sub_id,))
    db.commit()


def clear_nodes(sub_id):
    """Remove all nodes belonging to a subscription."""
    db = get_db()
    db.execute('DELETE FROM nodes WHERE sub_id = ?', (sub_id,))
    db.commit()


def batch_insert_nodes(sub_id, nodes):
    """Insert a list of node dicts for *sub_id* in one transaction."""
    db = get_db()
    db.executemany(
        '''INSERT INTO nodes
           (sub_id, name, protocol, address, port, config_json, bin_type)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        [(sub_id, n['name'], n['protocol'], n['address'], n['port'],
          n['config_json'], n['bin_type']) for n in nodes]
    )
    db.commit()
