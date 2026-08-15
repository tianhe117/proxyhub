#!/usr/bin/env python3
"""一次性迁移脚本（可重复执行）。

删除已废弃的 DB 结构：
- nodes 表的 latency 三列（tcp_latency / curl_latency / last_check_at）
- services 表的 status 列（运行时状态，改实时查进程）与 created_at 列（死字段）
- outbounds 表的 type / config_json 列（出站改纯关系，direct 走 service.outbound_id=0）
- 废弃的 _schema / settings 表

用法：
    python3 scripts/migrate_db.py
"""

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.settings import get_db_path

NODE_DROP_COLS = ('tcp_latency', 'curl_latency', 'last_check_at')

db = sqlite3.connect(get_db_path())
db.row_factory = sqlite3.Row

# nodes 表删 latency 三列
node_cols = {r[1] for r in db.execute('PRAGMA table_info(nodes)')}
for col in NODE_DROP_COLS:
    if col in node_cols:
        db.execute(f'ALTER TABLE nodes DROP COLUMN {col}')

# services 表删 status / created_at 列（status 改实时查进程，created_at 为死字段）
svc_cols = {r[1] for r in db.execute('PRAGMA table_info(services)')}
for col in ('status', 'created_at'):
    if col in svc_cols:
        db.execute(f'ALTER TABLE services DROP COLUMN {col}')

# outbounds 表：direct → service.outbound_id=0；single 的 config_json.node_id → outbound_nodes
ob_cols = {r[1] for r in db.execute('PRAGMA table_info(outbounds)')}
if 'type' in ob_cols:
    direct_rows = [r for r in db.execute("SELECT * FROM outbounds WHERE type = 'direct'")]
    for row in direct_rows:
        # 被该 direct 出站引用的 service 改直连（outbound_id=0）
        db.execute('UPDATE services SET outbound_id = 0 WHERE outbound_id = ?', (row['id'],))
        db.execute('DELETE FROM outbound_nodes WHERE outbound_id = ?', (row['id'],))
        db.execute('DELETE FROM outbounds WHERE id = ?', (row['id'],))

    single_rows = [r for r in db.execute("SELECT * FROM outbounds WHERE type = 'single'")]
    for row in single_rows:
        cfg = row['config_json']
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except (json.JSONDecodeError, TypeError):
                cfg = {}
        nid = cfg.get('node_id') if isinstance(cfg, dict) else None
        if nid:
            db.execute(
                'INSERT INTO outbound_nodes (outbound_id, node_id, priority) VALUES (?, ?, 1)',
                (row['id'], nid),
            )

# outbounds 删 type / config_json 列
ob_cols = {r[1] for r in db.execute('PRAGMA table_info(outbounds)')}
for col in ('type', 'config_json'):
    if col in ob_cols:
        db.execute(f'ALTER TABLE outbounds DROP COLUMN {col}')

# 废弃表
db.execute('DROP TABLE IF EXISTS _schema')
db.execute('DROP TABLE IF EXISTS settings')

db.commit()
db.close()

print('done')

