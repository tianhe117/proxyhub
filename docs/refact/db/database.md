# database.py 重构设计

## 目标

清理 `app/db/database.py` 的残留机制，使连接管理与建表逻辑与「外部脚本迁移」的既定决策对齐；同时清理 `app/db/__init__.py` 的死导出。

## 现状

`database.py` 当前结构：

```python
SCHEMA_VERSION = 1            # 定义但从未被引用

def get_db() -> sqlite3.Connection   # thread-local 连接，WAL + foreign_keys
def close_db() -> None               # checkpoint + close
def init_db() -> None                # 建 _schema 版本表 → if current < 1 → _create_v1 → _seed_settings
def _create_v1(db)                   # executescript 建 7 张表（全部 IF NOT EXISTS）
def _seed_settings(db)               # INSERT OR IGNORE 默认 settings
```

`app/db/__init__.py` 当前：

```python
"""Data access layer for ProxyHub."""
from .database import get_db, close_db, init_db
```

## 问题清单

### 1. `SCHEMA_VERSION` 与 `_schema` 版本表是死代码

`SCHEMA_VERSION = 1` 定义了但 `init_db` 里硬编码 `if current < 1` / `VALUES (1)`，常量从未被引用。

这与「latency 移内存」时定的迁移策略**自相矛盾**：我们已选「外部一次性脚本迁移」（`scripts/migrate_db.py`），不引入运行时 `_migrate_v2`。但 `init_db` 里仍残留一套 `_schema` 版本表 + 版本判断骨架。

而 `_create_v1` 全部 `CREATE TABLE IF NOT EXISTS`，本身幂等 —— 这套版本机制当前**没驱动任何东西**，是纯残留。

### 2. `_seed_settings` 与 `settings` 表是死代码

`settings` 表的真实存储已在 `app/settings.py`（`data/setting.json` + 内存 `_store`）。全项目搜 `settings` 表的 SQL，只有 `_seed_settings` 一处 `INSERT OR IGNORE` 写，**没有任何 `SELECT / UPDATE / DELETE FROM settings`** —— 该表是死表，`_seed_settings` 是往死表写数据的死代码。

**方案**：连同 `settings` 表定义一起删。`_create_tables` 去掉 `CREATE TABLE settings`，删 `_seed_settings` 函数，`database.py` 顶部 import 去掉 `DEFAULT_SETTINGS`（仅它用）。

### 3. `db/__init__.py` 的导出是死代码

全项目 28 处 db import 全部直指子模块（`from app.db.node import ...`、`from app.db.database import ...`），**没有任何一处 `from app.db import ...`**。`__init__.py` 里那三行导出无人使用。

### 4. `PRAGMA foreign_keys=ON` 空转（保持现状）

开了外键开关，但所有表都没有 `FOREIGN KEY ... REFERENCES` 约束，引用完整性全由应用层维护（如 `db/subscription.py` 手动级联删除）。

**结论**：保持现状不改。单人项目 + 应用层已维护约束，加 DB 外键收益有限、还可能因存量孤儿行报错。仅记录此现状，不算 bug。

### 5. 每请求 `wal_checkpoint(TRUNCATE)`（保持现状）

`close_db` 每次 checkpoint TRUNCATE。低流量项目下略重，但换来 WAL 文件不堆积，是合理权衡，不动。

## 重构方案

### `database.py` 精简

删掉版本机制与 settings 死表，`init_db` 退化为「幂等建表」，`_create_v1` 改名 `_create_tables`（名字不再暗示版本序列）：

```python
def init_db():
    """Create tables (idempotent)."""
    db = get_db()
    _create_tables(db)

def _create_tables(db):
    """Create all tables (§3.1)."""
    db.executescript('''... 6 张表 ...''')
```

删除：

- `SCHEMA_VERSION = 1` 常量
- `_schema` 表相关逻辑（`CREATE TABLE IF NOT EXISTS _schema`、`SELECT MAX(version)`、`if current < 1`、`INSERT OR REPLACE`）
- `_seed_settings` 函数 + `settings` 表定义（`CREATE TABLE settings`）
- 顶部 import 的 `DEFAULT_SETTINGS`（仅 `_seed_settings` 用）
- 改名 `_create_v1` → `_create_tables`（函数体不变，剩余 6 张表仍全部 `IF NOT EXISTS`）

`init_db` 不再 seed，settings 统一走 `app/settings.py` 的 JSON 存储。

### `db/__init__.py` 改纯 docstring

```python
"""Data access layer for ProxyHub.

子模块一表一文件（node / inbound / outbound / service / subscription），
调用方直接 `from app.db.<table> import <fn>`；本包不做聚合导出。
"""
```

删除 `from .database import get_db, close_db, init_db`。

理由：db 层「一表一模块」的 `list_all` / `get_by_id` / `create` / `update` / `delete` 在 6 个文件里全部重名，扁平聚合会互相覆盖，无法也无需包级导出。与 `app/services/__init__.py`（现为一行 docstring）对齐。

### 遗留死表清理（可选）

旧库 `data/proxyhub.db` 中已存在 `_schema` 和 `settings` 表。`_create_tables` 不再建它们后，旧表仍在但无害。可在 `scripts/migrate_db.py` 中顺手追加 `DROP TABLE IF EXISTS _schema` / `DROP TABLE IF EXISTS settings`，一次性清掉。

## 改动清单

| 文件 | 改动 |
|------|------|
| `app/db/database.py` | 删 `SCHEMA_VERSION`、`_schema` 版本逻辑、`_seed_settings`、`settings` 表、`DEFAULT_SETTINGS` import；`_create_v1` 改名 `_create_tables`；`init_db` 精简为 `_create_tables` |
| `app/db/__init__.py` | 删 `from .database import ...`，改为纯 docstring |
| `scripts/migrate_db.py`（可选） | 追加 `DROP TABLE IF EXISTS _schema` / `DROP TABLE IF EXISTS settings` |

## 验证

```bash
# 建库幂等：全新库 + 已有库各跑一次 init_db 不报错、表结构一致
python3 -c "
from app.db.database import init_db, get_db, close_db
init_db(); close_db()
print('init_db OK')
"

# 无残留引用（应无输出）
grep -rn "SCHEMA_VERSION\|_schema\|_seed_settings\|from app.db import" app/ scripts/

# 全应用 import 冒烟
python3 -c "import app.routes"

# 现有表数据完好（settings/_schema 已清）
python3 -c "
import sqlite3
c = sqlite3.connect('data/proxyhub.db')
print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\")])
"
```
