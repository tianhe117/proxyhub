# outbound 建模重构设计

## 目标

消除 `outbounds` 表的三个冗余设计（`type` 枚举、空壳 `config_json`、隐含的 `node_id`），把出站收敛为「纯关系」，direct 从「伪造的出站类型」还原为「service 层的连接方式」。

## 现状

```sql
outbounds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,              -- single / auto / direct
    config_json TEXT NOT NULL DEFAULT '{}'  -- single 存 node_id，auto/direct 存 {}
)

outbound_nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    outbound_id INTEGER NOT NULL,
    node_id     INTEGER NOT NULL,
    priority    INTEGER DEFAULT 0
)
```

### 现状的三个问题

1. **`type` 枚举冗余**：`single` 和 `auto` 的行为差异，代码里本就靠「节点数量」判断（`service_manager.py:516` `if len(pool) <= 1: continue`）。即使标 `auto`，池里 1 个节点时 failover 什么也不做，与 `single` 完全等价。`type` 只是把这个隐含规则重复存了一遍。

2. **`config_json` 是空壳**：唯一用途是 single 存 `node_id`（`{"node_id": 42}`），auto/direct 都是 `{}`。它叫「配置 JSON」却只塞一个外键，语义错位。一旦 `node_id` 独立，它就三种类型全空。

3. **`direct` 是伪造类型**：direct 从来不是「一组节点」，是「不走出站」。现在用 `type='direct'` 硬造一行 outbound 来代表它，是为了显式而牺牲诚实。代码里 direct 的实现其实是合成一个 `protocol='direct'` 的节点（`config_service.py:44`），`engine/xray.py` 早已支持 `direct/freedom` 协议。

## 目标模型

```sql
outbounds (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
)

outbound_nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    outbound_id INTEGER NOT NULL,
    node_id     INTEGER NOT NULL,
    priority    INTEGER DEFAULT 0
)

services (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    inbound_id  INTEGER NOT NULL,
    outbound_id INTEGER NOT NULL,   -- 0 = direct 直连
    auto_start  INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
)
```

### 语义（全部由数据推导，无枚举）

| 状态 | 表达 |
|------|------|
| direct 直连 | `service.outbound_id = 0` |
| 未配置出站 | outbound 存在但 `outbound_nodes` 无关联节点（应用层兜底报错） |
| single | outbound 关联 **1** 个节点 |
| auto（failover） | outbound 关联 **≥2** 个节点 |

### `outbound_id = 0` 表示 direct 的正当性

- 与项目既有哨兵惯例一致：`nodes.sub_id=0`（自定义）、failover `current_node_id=0`（未初始化）
- `INTEGER PRIMARY KEY AUTOINCREMENT` 从 1 起、永不生成 0，`0` 与真实 id 绝不冲突
- `services.outbound_id` 保持 `NOT NULL` 不用改（直连是显式存 `0`，不是 NULL）
- 显式性由「字段注释 + 前端 label（`<option value="0">Direct</option>`）+ config_service 分支注释」兜住，不必塞回 schema

### 前端

- **outbounds 界面**：不再有 type 下拉、direct 类型；只管理「名称 + 节点池」
- **service 界面**：Outbound 下拉框顶部加 `<option value="0">Direct（直连）</option>`，其余为各 outbound

## 改动清单

| 层 | 文件 | 改动 |
|----|------|------|
| schema | `db/database.py` | outbounds 删 `type`/`config_json` 列 |
| 迁移 | `scripts/migrate_db.py` | outbounds 删 `type`/`config_json`；存量 `type='direct'` 的 outbound 若被 service 引用，把该 service 的 `outbound_id` 改 0、删掉该 outbound 行；存量 single 的 `config_json.node_id` 迁移成 `outbound_nodes` 一行 |
| db 层 | `db/outbound.py` | `create(name)` 去掉 type/config_json 参数；`list_single_outbounds_by_node` 改 `SELECT ... WHERE node_id=?`（遍历 outbound_nodes）；`update` allowed 只留 name |
| db 层 | `db/service.py` | `create/update` 允许 `outbound_id=0`（direct） |
| service 层 | `outbound_service.py` | `create_outbound(name)` 去 type/config_json；删 direct/single/auto 校验 |
| service 层 | `config_service.py` | `get_outbound_node` 改：`outbound_id==0` → 合成 direct 节点；否则按 outbound 关联节点数（1→取它，≥2→pool[0] 或 failover 覆盖） |
| service 层 | `service_manager.py` | `outbound['type']=='auto'` 判断改「关联节点数 ≥2」；`=='direct'` 判断改 `outbound_id==0` |
| routes | `api_outbounds.py` | create/update 去 type/config_json；`TYPE_ORDER` 排序删（或改为按 id/名称） |
| 前端 | `outbounds.html` / `dashboard.html` | outbound 表单去 type 下拉、节点单选改池多选；service 下拉加 Direct 选项 |

## 关键迁移逻辑（scripts/migrate_db.py）

```python
# 1. 存量 single：config_json.node_id → outbound_nodes 一行
# 2. 存量 auto：outbound_nodes 已有数据，不动
# 3. 存量 direct：被 service 引用的 → service.outbound_id=0；删除该 direct outbound 行
# 4. ALTER outbounds DROP COLUMN type / config_json
```

> SQLite 3.35+ 支持 `DROP COLUMN`（本项目 3.37.2）。若删列后 outbound 行全空（只剩 id+name），无碍。

## 验证

```bash
# 迁移后 schema
python3 -c "import sqlite3; c=sqlite3.connect('data/proxyhub.db'); print([r[1] for r in c.execute('PRAGMA table_info(outbounds)')])"

# 语义验证（人工）：single 出站显示 1 节点、auto 显示多节点、service 选 0 走直连
python3 -c "import app.routes"
```

## 边界 / 不做

- 不做 `FOREIGN KEY` 约束（沿用「应用层维护引用完整性」约定）
- 不做「outbound 必须有 ≥1 节点」的 DB 约束，空 outbound 由应用层兜底
- 前端重写前，本次只落 schema + 后端，前端改动标记为待办
