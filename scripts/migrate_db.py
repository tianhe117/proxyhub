#!/usr/bin/env python3
"""一次性迁移脚本（可重复执行）。

删除已废弃的 DB 结构：
- nodes 表的 latency 三列（tcp_latency / curl_latency / last_check_at）
- services 表的 status 列（运行时状态，改实时查进程）
- 废弃的 _schema / settings 表

用法：
    python3 scripts/migrate_db.py
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.settings import get_db_path

NODE_DROP_COLS = ('tcp_latency', 'curl_latency', 'last_check_at')

db = sqlite3.connect(get_db_path())

# nodes 表删 latency 三列
node_cols = {r[1] for r in db.execute('PRAGMA table_info(nodes)')}
for col in NODE_DROP_COLS:
    if col in node_cols:
        db.execute(f'ALTER TABLE nodes DROP COLUMN {col}')

# services 表删 status 列
svc_cols = {r[1] for r in db.execute('PRAGMA table_info(services)')}
if 'status' in svc_cols:
    db.execute('ALTER TABLE services DROP COLUMN status')

# 废弃表
db.execute('DROP TABLE IF EXISTS _schema')
db.execute('DROP TABLE IF EXISTS settings')

db.commit()
db.close()

print('done')
