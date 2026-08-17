"""Outbound + outbound_nodes CRUD operations.

Outbound dict structure (sqlite3.Row → dict):
    id          int    primary key
    name        str    display name

outbound_nodes (pool entry) structure:
    id          int    primary key
    outbound_id int    parent outbound id
    node_id     int    pooled node id
    priority    int    lower = higher failover priority

outbound_fallback structure:
    outbound_id int    primary key (at most one per outbound)
    node_id     int    quick-switch fallback node id

Semantics are derived from data, no type enum:
    direct  → service.outbound_id = 0
    single  → outbound with 1 pool node
    auto    → outbound with >=2 pool nodes (failover)

Note: "fallback" = the quick-switch node (entity); "failover" = the
switching mechanism (logic).  The two are separate concerns.
"""

from .database import get_db


# ---------------------------------------------------------------------------
# Outbounds
# ---------------------------------------------------------------------------

def list_all():
    """Return all outbounds ordered by id (includes id=0 direct sentinel)."""
    db = get_db()
    return db.execute('SELECT * FROM outbounds ORDER BY id').fetchall()


def get_by_id(out_id):
    """Return an outbound by id, or None."""
    db = get_db()
    return db.execute('SELECT * FROM outbounds WHERE id = ?', (out_id,)).fetchone()


def list_outbounds_by_node(node_id):
    """Return outbounds that reference *node_id* (via outbound_nodes)."""
    db = get_db()
    return db.execute(
        '''SELECT DISTINCT o.id, o.name
           FROM outbounds o
           JOIN outbound_nodes onr ON onr.outbound_id = o.id
           WHERE onr.node_id = ?''',
        (node_id,)
    ).fetchall()


def create(name):
    """Insert an outbound and return its id."""
    db = get_db()
    cur = db.execute('INSERT INTO outbounds (name) VALUES (?)', (name,))
    db.commit()
    return cur.lastrowid


def update(out_id, **fields):
    """Update mutable fields on an outbound."""
    allowed = {'name'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    sets = ', '.join(f'{k} = ?' for k in updates)
    vals = list(updates.values()) + [out_id]
    db = get_db()
    db.execute(f'UPDATE outbounds SET {sets} WHERE id = ?', vals)
    db.commit()


def delete(out_id):
    """Delete an outbound (pool/fallback refs cascade via FK; id=0 reserved)."""
    db = get_db()
    db.execute('DELETE FROM outbounds WHERE id = ? AND id > 0', (out_id,))
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
                  n.name, n.protocol, n.address, n.port, n.bin_type
           FROM outbound_nodes onr
           JOIN nodes n ON n.id = onr.node_id
           WHERE onr.outbound_id = ?
           ORDER BY onr.priority ASC''',
        (outbound_id,)
    ).fetchall()


def add_pool_node(outbound_id, node_id, priority=None):
    """Add a node to an outbound's pool and return the pool entry id.

    *priority* defaults to None = auto-assign to the end of the pool.
    """
    db = get_db()
    if priority is None:
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


# ---------------------------------------------------------------------------
# Outbound fallback (quick-switch node)
# ---------------------------------------------------------------------------

def get_fallback_node(outbound_id):
    """Return the fallback node for an outbound, or None."""
    db = get_db()
    return db.execute(
        'SELECT * FROM outbound_fallback WHERE outbound_id = ?', (outbound_id,)
    ).fetchone()


def set_fallback_node(outbound_id, node_id):
    """Set (or clear, when node_id=0) the fallback node for an outbound."""
    db = get_db()
    if node_id == 0:
        db.execute('DELETE FROM outbound_fallback WHERE outbound_id = ?', (outbound_id,))
    else:
        db.execute(
            '''INSERT INTO outbound_fallback (outbound_id, node_id) VALUES (?, ?)
               ON CONFLICT(outbound_id) DO UPDATE SET node_id = excluded.node_id''',
            (outbound_id, node_id)
        )
    db.commit()
