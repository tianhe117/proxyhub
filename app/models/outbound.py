"""Outbound + outbound_nodes CRUD operations."""

import json
from .database import get_db


# ---------------------------------------------------------------------------
# Outbounds
# ---------------------------------------------------------------------------

def list_all():
    """Return all outbounds ordered by id."""
    db = get_db()
    return db.execute('SELECT * FROM outbounds ORDER BY id').fetchall()


def get_by_id(out_id):
    """Return an outbound by id, or None."""
    db = get_db()
    return db.execute('SELECT * FROM outbounds WHERE id = ?', (out_id,)).fetchone()


def create(name, out_type, config_json=None):
    """Insert an outbound and return its id."""
    if config_json is None:
        config_json = {}
    if isinstance(config_json, dict):
        config_json = json.dumps(config_json)
    db = get_db()
    cur = db.execute(
        'INSERT INTO outbounds (name, type, config_json) VALUES (?, ?, ?)',
        (name, out_type, config_json)
    )
    db.commit()
    return cur.lastrowid


def update(out_id, **fields):
    """Update mutable fields on an outbound."""
    allowed = {'name', 'type', 'config_json'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if 'config_json' in updates and isinstance(updates['config_json'], dict):
        updates['config_json'] = json.dumps(updates['config_json'])
    if not updates:
        return
    sets = ', '.join(f'{k} = ?' for k in updates)
    vals = list(updates.values()) + [out_id]
    db = get_db()
    db.execute(f'UPDATE outbounds SET {sets} WHERE id = ?', vals)
    db.commit()


def delete(out_id):
    """Delete an outbound and its pool entries."""
    db = get_db()
    db.execute('DELETE FROM outbound_nodes WHERE outbound_id = ?', (out_id,))
    db.execute('DELETE FROM outbounds WHERE id = ?', (out_id,))
    db.commit()


# ---------------------------------------------------------------------------
# Outbound node pool
# ---------------------------------------------------------------------------

def get_pool_nodes(outbound_id):
    """Return pool entries for an outbound, joined with node details,
    ordered by priority ASC."""
    db = get_db()
    return db.execute(
        '''SELECT onr.id AS pool_id, onr.priority, onr.node_id,
                  n.name, n.protocol, n.address, n.port,
                  n.tcp_latency, n.curl_latency, n.bin_type
           FROM outbound_nodes onr
           JOIN nodes n ON n.id = onr.node_id
           WHERE onr.outbound_id = ?
           ORDER BY onr.priority ASC''',
        (outbound_id,)
    ).fetchall()


def add_pool_node(outbound_id, node_id, priority=0):
    """Add a node to an outbound's pool and return the pool entry id."""
    db = get_db()
    # Auto-assign priority to end if not specified
    if priority == 0:
        max_p = db.execute(
            'SELECT COALESCE(MAX(priority), 0) FROM outbound_nodes WHERE outbound_id = ?',
            (outbound_id,)
        ).fetchone()[0]
        priority = max_p + 1
    cur = db.execute(
        'INSERT INTO outbound_nodes (outbound_id, node_id, priority) VALUES (?, ?, ?)',
        (outbound_id, node_id, priority)
    )
    db.commit()
    return cur.lastrowid


def remove_pool_node(pool_id):
    """Remove a single pool entry by its id."""
    db = get_db()
    db.execute('DELETE FROM outbound_nodes WHERE id = ?', (pool_id,))
    db.commit()


def reorder_pool_nodes(outbound_id, node_order):
    """*node_order* is a list of pool entry ids in the new priority order."""
    db = get_db()
    for pri, pool_id in enumerate(node_order):
        db.execute(
            'UPDATE outbound_nodes SET priority = ? WHERE id = ? AND outbound_id = ?',
            (pri + 1, pool_id, outbound_id)
        )
    db.commit()


def sync_pool_nodes(outbound_id, node_ids):
    """Replace all pool nodes with the given node_ids in order."""
    db = get_db()
    db.execute('DELETE FROM outbound_nodes WHERE outbound_id = ?', (outbound_id,))
    for pri, nid in enumerate(node_ids):
        # Skip invalid node IDs
        exists = db.execute('SELECT 1 FROM nodes WHERE id = ?', (nid,)).fetchone()
        if not exists:
            continue
        db.execute(
            'INSERT INTO outbound_nodes (outbound_id, node_id, priority) VALUES (?, ?, ?)',
            (outbound_id, nid, pri + 1)
        )
    db.commit()
