#!/usr/bin/env python3
"""一次性迁移：删除 nodes 表的 latency 三列（可重复执行）。

用法：
    python3 scripts/migrate_latency.py
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.settings import get_db_path

DROP = ('tcp_latency', 'curl_latency', 'last_check_at')

db = sqlite3.connect(get_db_path())
cols = {r[1] for r in db.execute('PRAGMA table_info(nodes)')}
for col in DROP:
    if col in cols:
        db.execute(f'ALTER TABLE nodes DROP COLUMN {col}')
db.commit()
db.close()

print('done:', [r[1] for r in sqlite3.connect(get_db_path()).execute('PRAGMA table_info(nodes)')])
