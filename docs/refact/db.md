# db 层优化方案

## 目标

采用 Repository 模式（方案 B），把每张表的 CRUD 封装成类，替代当前扁平的函数式接口。

## 现状问题

1. 每个文件都是扁平的 `list_all`/`get_by_id`/`create`/`update`/`delete`，命名不统一（`get_by_id` vs `get_nodes_by_sub`、`update` vs `update_status`）
2. 无内聚、无类型、难 mock、难测试
3. 延迟字段（`tcp_latency`/`curl_latency`/`last_check_at`）仍写 DB，待移到内存

## 目标结构

```
app/db/
├── __init__.py       # 聚合导出各 repo 单例
├── database.py       # 连接管理 + 迁移（不动）
├── node.py           # NodeRepo
├── inbound.py        # InboundRepo
├── outbound.py       # OutboundRepo（含 pool 方法）
├── service.py        # ServiceRepo
└── subscription.py   # SubscriptionRepo（含节点同步）
```

## Repository 类模式

每张表一个类，模块级单例：

```python
class NodeRepo:
    def list(self) -> list[dict]: ...
    def get(self, node_id) -> dict: ...
    def create(self, sub_id, name, protocol, address, port, config_json, bin_type) -> int: ...
    def update(self, node_id, **fields): ...
    def delete(self, node_id): ...
    def delete_all(self): ...
    # 延迟不再存 DB，删除 update_latency

node_repo = NodeRepo()
```

### 各 Repo 职责

| Repo | 方法 |
|------|------|
| `NodeRepo` | list / list_by_sub / list_grouped / get / create / update / delete / delete_all |
| `InboundRepo` | list / get / create / update / delete |
| `OutboundRepo` | list / get / create / update / delete + pool 方法（get_pool_nodes / add_pool_node / remove_pool_node / reorder_pool_nodes / sync_pool_nodes） |
| `ServiceRepo` | list / get / create / update / delete / update_status / get_auto_start_services |
| `SubscriptionRepo` | list / get / create / update / delete + 节点同步（clear_nodes / batch_insert_nodes / get_nodes_by_sub / sync_nodes） |

## 命名统一

| 旧 | 新 |
|----|----|
| `get_by_id(id)` | `get(id)`（类内 id 语义已明确） |
| `list_all()` | `list()` |
| `update_status(svc_id, status)` | `update_status(status)`（svc_id 通过实例或参数保留） |
| `get_nodes_by_sub(sub_id)` | `list_by_sub(sub_id)` |

## 调用方适配

| 旧 | 新 |
|----|----|
| `from app.db.node import get_by_id` | `from app.db import node_repo; node_repo.get(...)` |
| `from app.db.node import list_all` | `node_repo.list()` |

约 20+ 文件需要改 import。建议一次性全局替换，配合 `__init__.py` 聚合导出。

## 延迟字段移除（配合内存方案）

- `NodeRepo` 删除 `update_latency`
- nodes 表删除 `tcp_latency`/`curl_latency`/`last_check_at` 列（schema v2 迁移）
- 延迟改存内存（后续单独 state.py）

## 实施顺序

1. 定义 5 个 Repo 类 + 单例（保持原函数逻辑，只改封装）
2. `__init__.py` 聚合导出 repo 单例
3. 全局替换调用方 import
4. schema v2 迁移删除延迟列 + settings 表（独立步骤）

## 验证

1. `python3 test/test_checker.py`
2. 启动应用，节点/入站/出站/服务/订阅 CRUD 正常
