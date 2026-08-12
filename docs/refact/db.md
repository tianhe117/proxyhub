# DB 层优化

## 目标

1. Node 类型化：dataclass 替代 dict
2. DB 只存节点数据，延迟从 DB 移除、改为内存存储
3. 清理 settings 残留（已迁移到 JSON）

## 现状文件审查

### `database.py` — 🟡 死代码

- `from app.settings import DEFAULT_SETTINGS` 只用于 `_seed_settings`
- `_create_v1` 创建 `settings` 表 —— settings 已迁 JSON，表不需要了
- `_seed_settings` 写入 settings 默认值 —— 不需要了
- 无其他问题（thread-local 连接、WAL、迁移框架都干净）

**改动**：删 settings 表、`_seed_settings()`、`DEFAULT_SETTINGS` import。

### `node.py` — 🟡 延迟字段残留

- `update()` 的 `allowed` 集合含 `tcp_latency`、`curl_latency`、`last_check_at`
- `update_latency()` 整个函数是写延迟到 DB 的唯一入口
- CRUD 模式统一，无明显重复代码

**改动**：新增 Node dataclass；`allowed` 去延迟字段；删 `update_latency()`；CRUD 函数返回 Node 对象。

### `outbound.py` — 🟡 延迟 JOIN

- `get_pool_nodes` SQL 中 `SELECT ..., n.tcp_latency, n.curl_latency, n.bin_type`
- pool 管理逻辑干净，无需其他改动

**改动**：SQL 去 `tcp_latency`、`curl_latency` 两列。

### `subscription.py` — 🟢 逻辑重复（保留）

- `update_node` 和 `delete_node` 与 `node.py` 同名函数功能重叠
- 但这是避免循环引用的设计，保持现状

### `inbound.py` / `service.py` — 🟢 无需改动

- 无延迟引用，无 settings 引用，CRUD 模式统一

## DB schema 变更：v1 → v2

删除 `tcp_latency`、`curl_latency`、`last_check_at` 列；删除 `settings` 表。

```sql
CREATE TABLE nodes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sub_id        INTEGER DEFAULT 0,
    name          TEXT NOT NULL,
    protocol      TEXT NOT NULL,
    address       TEXT NOT NULL,
    port          INTEGER NOT NULL,
    config_json   TEXT NOT NULL,
    bin_type      TEXT DEFAULT 'xray'
);
```

迁移步骤（`_create_v2` + `_migrate_v1_to_v2`）：

1. `CREATE TABLE nodes_v2 (...)` 新表
2. `INSERT INTO nodes_v2 SELECT id,sub_id,name,protocol,address,port,config_json,bin_type FROM nodes`
3. `DROP TABLE nodes` → `ALTER TABLE nodes_v2 RENAME TO nodes`
4. `DROP TABLE IF EXISTS settings`
5. `SCHEMA_VERSION = 2`

## Node dataclass

定义在 `app/db/node.py`。

```python
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
```

`sqlite3.Row` → Node 在 `get_by_id()` / `list_all()` 中完成。调用方从 `node['field']` 改为 `node.field`。

## 延迟存储：app/state.py

纯内存 dict，进程生命周期。写方只有 checker（`service_manager.py`），读方是 API routes。

```python
_latency: dict[int, dict] = {}  # {node_id: {tcp: int, url: int, checked_at: str}}
```

## 文件变更汇总

| 文件 | 操作 |
|------|------|
| `app/state.py` | **新建**：内存延迟存储 |
| `app/db/node.py` | Node dataclass；删 `update_latency()`；allowed 去延迟字段；CRUD 返回 Node |
| `app/db/database.py` | schema v2：去 latency 列 + 删 settings 表 + 删 `_seed_settings()` |
| `app/db/outbound.py` | `get_pool_nodes` SQL 去 `tcp_latency`/`curl_latency` |
| `app/db/subscription.py` | 不动 |
| `app/db/inbound.py` / `service.py` | 不动 |
| `app/services/service_manager.py` | `update_latency` → `state.set_latency` |
| `app/routes/*.py` | 注入延迟数据到响应 |
| 全项目 | `node['field']` → `node.field`（~20 文件） |

## 验证

1. `python3 test/test_checker.py`
2. 启动应用：DB 自动迁移，节点列表正常（延迟显示 —）
3. 健康检查后延迟更新
