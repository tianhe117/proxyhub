# 引用完整性外键化 + 哨兵行设计

## 背景

`app/db/database.py` 已 `PRAGMA foreign_keys=ON`，但所有表均未声明 `FOREIGN KEY`，开关空转（见 `database.md` 问题 #4）。引用完整性全靠应用层手工维护，已出现多处不一致：

- `outbound_fallback` 表加入后，节点删除路径普遍漏清该表
- `db/node.py:delete` 级联删 `outbound_nodes`，但 `node_service.delete_node` 又「拒绝删除」——策略自相矛盾
- 删除节点路径有 5 条，新增一张引用表要改 5 处，极易漏

前提已明确：**结构基本不再变化 + 既有数据不重要**。这抹掉了外键方案的历史劣势（重建表迁移），使「外键化」成为最一劳永逸的答案：删除时的正确性由 DB 硬保证，反向引用查询由外键元数据自动推导，均不再依赖人记清单。

## 目标

1. 所有引用关系声明外键，删除时由 DB 自动级联或拦截，永不漏。
2. `direct` / `custom` 两个隐式哨兵值升级为**真实哨兵行**（`id=0`），使外键 100% 覆盖，无 partial foreign key 的 hack。
3. 提供一个通用接口：入参任意表任意行，递归返回所有引用它的子表行（含 `ON DELETE` 动作），用于删前看影响面。

## 引用全景

| 子表.列 | 父表 | ON DELETE | 理由 |
|---|---|---|---|
| `nodes.sub_id` | `subscriptions.id` | CASCADE | 删订阅连带删其节点（现状即如此） |
| `outbound_nodes.outbound_id` | `outbounds.id` | CASCADE | 池成员随出站消失 |
| `outbound_nodes.node_id` | `nodes.id` | CASCADE | 池成员随节点消失 |
| `outbound_fallback.outbound_id` | `outbounds.id` | CASCADE | 切换节点随出站消失 |
| `outbound_fallback.node_id` | `nodes.id` | CASCADE | 切换节点随节点消失 |
| `services.inbound_id` | `inbounds.id` | RESTRICT | 顶层业务实体，被引用时拦删 |
| `services.outbound_id` | `outbounds.id` | RESTRICT | 同上（`0` 指向 direct 哨兵行） |

级联链：删订阅 → CASCADE 删 nodes → CASCADE 删 outbound_nodes/outbound_fallback 中引用这些节点的行。删节点、删出站同理自动下沉。`services` 是链条终点，被引用时 RESTRICT 拦删。

## 哨兵行设计

### id=0 显式哨兵行（非 1）

`INTEGER PRIMARY KEY AUTOINCREMENT` 从 1 起、永不生成 0；显式插入 `id=0` 后真实行仍从 1 开始，哨兵与真实数据永不冲突。且现有代码的 `sub_id==0` / `outbound_id==0` 判断、`config_service.py:44` 的 `'id': 0`、前端 `value="0"` 的 Direct 选项**全部无需改动**——用 0 是最小侵入。

`init_db` 幂等插入两行：

```sql
INSERT OR IGNORE INTO subscriptions (id, name) VALUES (0, 'custom');
INSERT OR IGNORE INTO outbounds     (id, name) VALUES (0, 'direct');
```

### 哨兵行两条配套规则（必须，否则泄漏进业务）

1. **删除保护**：`subscriptions.delete` / `outbounds.delete` 用 `WHERE id > 0` 兜底，哨兵行只读、不可删（前端即使发删除请求也落在 db 层护栏上，删不掉）。
2. **语义定位**：哨兵行是「为满足外键而存在的占位父行」，非真实业务实体——custom 节点 `sub_id=0` 借它满足外键，direct service `outbound_id=0` 借它满足外键。

> 列表查询**不**过滤哨兵行：`list_all` 直接全量返回，哨兵行是一等公民。`direct` 让 service 下拉自动获得 Direct 选项；`custom` 让 `list_by_sub(0)` 无需特殊通道。由此引入的前端显示适配（订阅页/出站管理页过滤 id=0）登记在 upper-layer-todo，待前端重写时处理。

## 完整 DDL

```sql
CREATE TABLE IF NOT EXISTS subscriptions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    url              TEXT NOT NULL,
    filter_keywords  TEXT DEFAULT '',
    exclude_keywords TEXT DEFAULT '',
    updated_at       TEXT,
    upload_bytes     INTEGER DEFAULT 0,
    download_bytes   INTEGER DEFAULT 0,
    total_bytes      INTEGER DEFAULT 0,
    expire_at        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sub_id      INTEGER NOT NULL DEFAULT 0 REFERENCES subscriptions(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    protocol    TEXT NOT NULL,
    address     TEXT NOT NULL,
    port        INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    bin_type    TEXT DEFAULT 'xray'
);

CREATE TABLE IF NOT EXISTS inbounds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    protocol    TEXT NOT NULL,
    listen_addr TEXT DEFAULT '0.0.0.0',
    port        INTEGER NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS outbounds (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbound_nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    outbound_id INTEGER NOT NULL REFERENCES outbounds(id) ON DELETE CASCADE,
    node_id     INTEGER NOT NULL REFERENCES nodes(id)     ON DELETE CASCADE,
    priority    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS outbound_fallback (
    outbound_id INTEGER PRIMARY KEY REFERENCES outbounds(id) ON DELETE CASCADE,
    node_id     INTEGER NOT NULL        REFERENCES nodes(id)     ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS services (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    inbound_id  INTEGER NOT NULL REFERENCES inbounds(id)  ON DELETE RESTRICT,
    outbound_id INTEGER NOT NULL REFERENCES outbounds(id) ON DELETE RESTRICT,
    auto_start  INTEGER DEFAULT 0
);
```

> `nodes.sub_id` 与 `services.outbound_id` 的哨兵值 0 现在指向真实哨兵行，外键可正常约束，无需 partial foreign key。

## 反向引用查询（通用接口）

外键不建反向索引，DB 也**不提供**「给定父表，反向列出引用它的子表」的一键查询。但外键定义存在 schema 元数据里，可用 `PRAGMA foreign_key_list(子表)` 读取，写一个通用接口自动推导（放在 `app/db/references.py`，跨表通用，不属「一表一模块」）：

```python
"""反向引用查询：任意表任意行 → 递归返回引用它的子表行。

依赖外键声明（PRAGMA foreign_key_list 读取元数据）。
"""

from .database import get_db


def _tables(db):
    return [r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )]


def list_incoming_references(db, table, row_id):
    """直接引用：返回引用 (table, row_id) 的所有子表行。

    返回：[{'table': 子表名, 'column': 外键列, 'row_id': 子表行主键,
            'on_delete': CASCADE/RESTRICT/..., 'rows': [Row, ...]}, ...]
    """
    refs = []
    for t in _tables(db):
        for fk in db.execute(f'PRAGMA foreign_key_list({t})'):
            if fk['table'] != table:
                continue
            col = fk['from']
            rows = db.execute(f'SELECT * FROM {t} WHERE {col} = ?', (row_id,)).fetchall()
            if rows:
                refs.append({
                    'table': t, 'column': col,
                    'row_id': rows[0]['id'],          # 假定主键列 id（本项目统一）
                    'on_delete': fk['on_delete'],
                    'rows': rows,
                })
    return refs


def tree_incoming_references(db, table, row_id, visited=None):
    """递归展开：返回 (table, row_id) 的完整反向依赖树。

    每个节点含 on_delete，调用方据此区分「会级联删」与「会拦删」。
    visited 按 (table, row_id) 去重，防环。
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
            'table': ref['table'], 'column': ref['column'],
            'row_id': ref['row_id'], 'on_delete': ref['on_delete'],
            'refs': tree_incoming_references(db, ref['table'], ref['row_id'], visited),
        })
    return result
```

调用 `tree_incoming_references(db, 'nodes', 42)` 得到整条依赖链：node → outbound_nodes/outbound_fallback → outbound → services。`on_delete` 字段区分 CASCADE（会跟着删）与 RESTRICT（会拦删）。

> 本项目所有表主键列统一为 `id`，故 `row_id` 硬取 `rows[0]['id']`。若未来有异名主键，需按 `PRAGMA table_info` 的 `pk` 列定位，当前无需。

## 迁移：DROP 重建（数据不重要）

数据不重要 + 结构基本稳定 → 不做逐表 ALTER 重建，直接**删库重建**，`init_db` 用新 DDL 重建所有表并 seed 哨兵行。`scripts/migrate_db.py` 可改为：

```python
# 旧库直接丢弃，由 init_db 重建（外键 + 哨兵行）
import os
from app.settings import get_db_path
for suffix in ('', '-wal', '-shm'):
    try:
        os.remove(get_db_path() + suffix)
    except FileNotFoundError:
        pass
print('old db dropped; run init_db to rebuild')
```

> 若后续想保留数据，再补逐表 12 步 copy→drop→rename 迁移；当前数据不重要，不做。

## 改动清单

| 文件 | 改动 |
|------|------|
| `app/db/database.py` | 全部建表加外键；`init_db` 末尾 seed 两行哨兵（`INSERT OR IGNORE ... id=0`） |
| `app/db/subscription.py` | `list_all` 全量返回（含 id=0 custom）；`delete` 用 `WHERE id > 0` 护栏 |
| `app/db/outbound.py` | `list_all` 全量返回（含 id=0 direct）；`delete` 用 `WHERE id > 0` 护栏 |
| `app/db/references.py`（新增） | `list_incoming_references` / `tree_incoming_references` 通用反向查询 |
| `app/db/node.py` | `delete` 删掉手写 `DELETE FROM outbound_nodes`（外键已级联）；`list_grouped` 跳过 id=0 哨兵（custom 仍以 `sub=None` 呈现） |
| `app/db/outbound.py` | `delete` 删掉手写 `DELETE FROM outbound_nodes`（外键已级联） |
| `app/db/subscription.py` | `delete`/`clear_nodes`/`delete_node` 删掉手写级联（外键已级联） |
| `scripts/migrate_db.py` | 改为删库重建 |

> 应用层 `node_service.delete_node` 的「拒绝删除」逻辑是否移除、`outbound_service.delete_outbound` 是否加「service 引用则拦」提示，属**应用层策略**，本次 DB 层方案不展开，另行登记。

## 验证

```bash
# 1. 全新库 init_db：外键生效 + 哨兵行就位
python3 -c "
from app.db.database import init_db, get_db, close_db
init_db()
db = get_db()
print('subs sentinel:', dict(db.execute('SELECT id,name FROM subscriptions WHERE id=0').fetchone()))
print('ob sentinel  :', dict(db.execute('SELECT id,name FROM outbounds WHERE id=0').fetchone()))
print('fk_check:', db.execute('PRAGMA foreign_key_check').fetchall())
close_db()
"

# 2. 级联验证：删 node → outbound_nodes/outbound_fallback 自动清
# 3. RESTRICT 验证：删被 service 引用的 outbound → 报 IntegrityError
# 4. 反向查询：tree_incoming_references(db,'nodes',42) 返回完整依赖树
# 5. 哨兵行不进列表：list_all() 结果无 id=0
```
