"""Reverse reference lookup: any table + row → its incoming references.

Relies on declared FOREIGN KEY constraints (read via PRAGMA
foreign_key_list).  Without FK declarations these queries return nothing.

This module is cross-table by nature, so it does not follow the
"one table, one module" layout of the rest of app.db.
"""

def _tables(db):
    """Return all user table names (excludes sqlite_* internals)."""
    return [r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )]


def _pk_column(db, table):
    """Return the primary key column name, or None if the table has no PK."""
    for r in db.execute(f'PRAGMA table_info({table})'):
        if r['pk']:
            return r['name']
    return None


def list_incoming_references(db, table, row_id):
    """Return direct incoming references to (table, row_id).

    Returns a list of dicts:
        {'table': child table name, 'column': FK column,
         'row_id': child row primary key, 'on_delete': FK action,
         'rows': [Row, ...]}
    """
    refs = []
    for t in _tables(db):
        pk = _pk_column(db, t)
        for fk in db.execute(f'PRAGMA foreign_key_list({t})'):
            if fk['table'] != table:
                continue
            col = fk['from']
            rows = db.execute(
                f'SELECT * FROM {t} WHERE {col} = ?', (row_id,)
            ).fetchall()
            if rows:
                refs.append({
                    'table': t,
                    'column': col,
                    'row_id': rows[0][pk] if pk else None,
                    'on_delete': fk['on_delete'],
                    'rows': rows,
                })
    return refs


def tree_incoming_references(db, table, row_id, visited=None):
    """Recursively expand the reverse dependency tree of (table, row_id).

    Each node carries on_delete so callers can distinguish CASCADE (will
    be deleted) from RESTRICT (will block deletion).  visited dedups on
    (table, row_id) to guard against cycles.
    """
    if visited is None:
        visited = set()
    key = (table, row_id)
    if key in visited:
        return []
    visited.add(key)

    result = []
    for ref in list_incoming_references(db, table, row_id):
        result.append({
            'table': ref['table'],
            'column': ref['column'],
            'row_id': ref['row_id'],
            'on_delete': ref['on_delete'],
            'refs': tree_incoming_references(db, ref['table'], ref['row_id'], visited),
        })
    return result
