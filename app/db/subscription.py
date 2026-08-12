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


def get_nodes_by_sub(sub_id):
    """Return all nodes for a subscription."""
    db = get_db()
    return db.execute(
        'SELECT * FROM nodes WHERE sub_id = ?', (sub_id,)
    ).fetchall()


def update_node(node_id, **fields):
    """Update fields on a node."""
    allowed = {'name', 'protocol', 'address', 'port', 'config_json', 'bin_type'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    sets = ', '.join(f'{k} = ?' for k in updates)
    vals = list(updates.values()) + [node_id]
    db = get_db()
    db.execute(f'UPDATE nodes SET {sets} WHERE id = ?', vals)


def delete_node(node_id):
    """Delete a node and its outbound references."""
    db = get_db()
    db.execute('DELETE FROM outbound_nodes WHERE node_id = ?', (node_id,))
    db.execute('DELETE FROM nodes WHERE id = ?', (node_id,))


def sync_nodes(sub_id, new_nodes):
    """Sync nodes for a subscription using name as matching key.

    - name exists in both: UPDATE config
    - name only in old: DELETE
    - name only in new: INSERT

    Returns:
        dict: {updated, deleted, inserted}
    """
    old_nodes = get_nodes_by_sub(sub_id)
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
        # Update existing nodes
        for node_id, new in to_update:
            update_node(node_id,
                        protocol=new['protocol'],
                        address=new['address'],
                        port=new['port'],
                        config_json=new['config_json'],
                        bin_type=new['bin_type'])

        # Delete removed nodes
        for node_id in to_delete:
            delete_node(node_id)

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
