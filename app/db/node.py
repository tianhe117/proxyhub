"""Node CRUD operations."""

import json
from dataclasses import dataclass, asdict
from .database import get_db


@dataclass
class Node:
    id: int
    name: str
    address: str
    port: int
    protocol: str
    bin_type: str
    config_json: str = '{}'
    sub_id: int = 0

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def to_dict(self):
        return asdict(self)


def _row_to_node(row) -> Node:
    return Node(
        id=row['id'],
        name=row['name'],
        address=row['address'],
        port=row['port'],
        protocol=row['protocol'],
        bin_type=row['bin_type'],
        config_json=row['config_json'],
        sub_id=row['sub_id'],
    )


def list_all():
    db = get_db()
    return [_row_to_node(r) for r in
            db.execute('SELECT * FROM nodes ORDER BY sub_id, id').fetchall()]


def list_by_sub(sub_id):
    db = get_db()
    return [_row_to_node(r) for r in
            db.execute('SELECT * FROM nodes WHERE sub_id = ? ORDER BY id', (sub_id,)).fetchall()]


def list_grouped():
    from .subscription import list_all as list_all_subs

    groups = []
    custom_nodes = list_by_sub(0)
    if custom_nodes:
        groups.append({'sub': None, 'nodes': custom_nodes, 'count': len(custom_nodes)})

    for sub in list_all_subs():
        nodes = list_by_sub(sub['id'])
        groups.append({'sub': sub, 'nodes': nodes, 'count': len(nodes)})

    return groups


def get_by_id(node_id):
    db = get_db()
    row = db.execute('SELECT * FROM nodes WHERE id = ?', (node_id,)).fetchone()
    return _row_to_node(row) if row else None


def create(sub_id, name, protocol, address, port, config_json, bin_type='xray'):
    if isinstance(config_json, dict):
        config_json = json.dumps(config_json)
    db = get_db()
    cur = db.execute(
        '''INSERT INTO nodes
           (sub_id, name, protocol, address, port, config_json, bin_type)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (sub_id, name, protocol, address, int(port), config_json, bin_type)
    )
    db.commit()
    return cur.lastrowid


def update(node_id, **fields):
    allowed = {'name', 'protocol', 'address', 'port', 'config_json', 'bin_type'}
    updates = {k: v for k, v in fields.items() if k in allowed}
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
    db = get_db()
    db.execute('DELETE FROM nodes WHERE id = ?', (node_id,))
    db.commit()


def delete_all():
    db = get_db()
    db.execute('DELETE FROM nodes')
    db.commit()


def update_latency(node_id, tcp_latency, curl_latency, check_time):
    db = get_db()
    db.execute(
        'UPDATE nodes SET tcp_latency=?, curl_latency=?, last_check_at=? WHERE id=?',
        (tcp_latency, curl_latency, check_time, node_id)
    )
    db.commit()
