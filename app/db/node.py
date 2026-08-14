"""Node CRUD operations.

Node dict structure (sqlite3.Row → dict):
    id          int       primary key
    sub_id      int       subscription id, 0 = custom
    name        str       display name
    protocol    str       vmess / vless / trojan / ss / ssr / anytls /
                          hysteria / hysteria2 / tuic / direct
    address     str       remote server address
    port         int        remote server port
    config_json str       JSON string, protocol-specific config
    bin_type    str       xray / sslocal / sing-box

Latency is stored in-memory (app.utils.latency), not in the DB.
"""

import json
from .database import get_db


def list_all():
    """Return every node ordered by sub_id, id."""
    db = get_db()
    return db.execute('SELECT * FROM nodes ORDER BY sub_id, id').fetchall()


def list_by_sub(sub_id):
    """Return nodes for a specific subscription (or custom nodes when sub_id=0)."""
    db = get_db()
    return db.execute(
        'SELECT * FROM nodes WHERE sub_id = ? ORDER BY id', (sub_id,)
    ).fetchall()


def list_grouped():
    """Return nodes grouped by subscription.

    Returns a list of dicts:
        {sub: subscription_row | None, nodes: [node_row, ...], count: int}
    Custom nodes (sub_id=0) appear as sub=None.
    """
    from .subscription import list_all as list_all_subs
    db = get_db()

    groups = []

    # Custom nodes first (sub_id = 0)
    custom_nodes = list_by_sub(0)
    if custom_nodes:
        groups.append({'sub': None, 'nodes': custom_nodes, 'count': len(custom_nodes)})

    # Then each subscription
    for sub in list_all_subs():
        nodes = list_by_sub(sub['id'])
        groups.append({'sub': sub, 'nodes': nodes, 'count': len(nodes)})

    return groups


def get_by_id(node_id):
    """Return a node by id, or None."""
    db = get_db()
    return db.execute('SELECT * FROM nodes WHERE id = ?', (node_id,)).fetchone()


def create(sub_id, name, protocol, address, port, config_json, bin_type='xray'):
    """Insert a node and return its id."""
    db = get_db()
    if isinstance(config_json, dict):
        config_json = json.dumps(config_json)
    cur = db.execute(
        '''INSERT INTO nodes
           (sub_id, name, protocol, address, port, config_json, bin_type)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (sub_id, name, protocol, address, int(port), config_json, bin_type)
    )
    db.commit()
    return cur.lastrowid


def update(node_id, **fields):
    """Update mutable fields on a node."""
    allowed = {'name', 'protocol', 'address', 'port', 'config_json', 'bin_type'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if 'port' in updates:
        updates['port'] = int(updates['port'])
    if 'config_json' in updates and isinstance(updates['config_json'], dict):
        updates['config_json'] = json.dumps(updates['config_json'])
    if not updates:
        return
    sets = ', '.join(f'{k} = ?' for k in updates)
    vals = list(updates.values()) + [node_id]
    db = get_db()
    db.execute(f'UPDATE nodes SET {sets} WHERE id = ?', vals)
    db.commit()


def delete(node_id):
    """Delete a single node."""
    db = get_db()
    db.execute('DELETE FROM nodes WHERE id = ?', (node_id,))
    db.commit()


def delete_all():
    """Delete every node from the database."""
    db = get_db()
    db.execute('DELETE FROM nodes')
    db.commit()
