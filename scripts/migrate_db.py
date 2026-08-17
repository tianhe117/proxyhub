#!/usr/bin/env python3
"""一次性迁移脚本：删库重建（外键 + 哨兵行）。

旧库结构已不适用（外键需重建表），且数据不重要，直接丢弃旧库，
由 init_db 按新 DDL 重建并 seed 哨兵行。

用法：
    python3 scripts/migrate_db.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.settings import get_db_path

# 丢弃旧库（含 WAL/SHM 副文件）
for suffix in ('', '-wal', '-shm'):
    try:
        os.remove(get_db_path() + suffix)
    except FileNotFoundError:
        pass

from app.db.database import init_db
init_db()

print('done: db rebuilt with foreign keys + sentinel rows')
