"""Subscription CRUD operations.

Subscription dict structure (sqlite3.Row → dict):
    id               int    primary key
    name             str    display name
    url              str    subscription source URL
    filter_keywords  str    include keywords (newline/comma separated)
    exclude_keywords str    exclude keywords (newline/comma separated)
    updated_at       str    ISO timestamp of last refresh
    upload_bytes     int    traffic quota (from Subscription-Userinfo)
    download_bytes   int    traffic quota
    total_bytes      int    traffic quota
    expire_at        int    unix timestamp
"""

from .database import get_db
from .node import list_by_sub


def list_all():
    """Return all subscriptions ordered by id (includes id=0 custom sentinel)."""
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
    """Delete a subscription (its nodes cascade via FK; id=0 reserved)."""
    db = get_db()
    db.execute('DELETE FROM subscriptions WHERE id = ? AND id > 0', (sub_id,))
    db.commit()


def clear_nodes(sub_id):
    """Remove all nodes belonging to a subscription."""
    db = get_db()
    db.execute('DELETE FROM nodes WHERE sub_id = ?', (sub_id,))
    db.commit()


def _update_node(node_id, **fields):
    """Update node fields without committing (private to sync_nodes)."""
    allowed = {'name', 'protocol', 'address', 'port', 'config_json', 'bin_type'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if 'port' in updates:
        updates['port'] = int(updates['port'])
    if not updates:
        return
    sets = ', '.join(f'{k} = ?' for k in updates)
    vals = list(updates.values()) + [node_id]
    db = get_db()
    db.execute(f'UPDATE nodes SET {sets} WHERE id = ?', vals)


def _delete_node(node_id):
    """Delete a node without committing (private to sync_nodes).

    outbound pool/fallback refs cascade via FK.
    """
    db = get_db()
    db.execute('DELETE FROM nodes WHERE id = ?', (node_id,))


def sync_nodes(sub_id, new_nodes):
    """Sync nodes for a subscription using name as matching key.

    - name exists in both: UPDATE config
    - name only in old: DELETE
    - name only in new: INSERT

    Matching by name keeps node ids stable, so outbound pool/fallback
    references survive refreshes.  New-side duplicate names collapse to
    the last occurrence (dict overwrite); dedup is expected upstream in
    the parser.

    Returns:
        dict: {updated, deleted, inserted}
    """
    old_nodes = list_by_sub(sub_id)
    old_map = {n['name']: dict(n) for n in old_nodes}
    new_map = {n['name']: n for n in new_nodes}

    to_update = []
    to_delete = []
    to_insert = []

    # Find updates and deletes
    for name, old in old_map.items():
        if name in new_map:
            new = new_map[name]
            to_update.append((old['id'], new))
        else:
            to_delete.append(old['id'])

    # Find inserts
    for name, new in new_map.items():
        if name not in old_map:
            to_insert.append(new)

    db = get_db()
    try:
        # Update existing nodes (deferred commit — one commit for the sync)
        for node_id, new in to_update:
            _update_node(node_id,
                         protocol=new['protocol'],
                         address=new['address'],
                         port=new['port'],
                         config_json=new['config_json'],
                         bin_type=new['bin_type'])

        # Delete removed nodes (FK cascades outbound pool/fallback refs)
        for node_id in to_delete:
            _delete_node(node_id)

        # Insert new nodes
        if to_insert:
            db.executemany(
                '''INSERT INTO nodes
                   (sub_id, name, protocol, address, port, config_json, bin_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                [(sub_id, n['name'], n['protocol'], n['address'], n['port'],
                  n['config_json'], n['bin_type']) for n in to_insert]
            )

        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        'updated': len(to_update),
        'deleted': len(to_delete),
        'inserted': len(to_insert),
    }
