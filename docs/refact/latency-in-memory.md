# latency 移内存方案

## 目标

节点延迟（TCP / URL）不落 DB，改为**进程内内存存储**。app 启动时为空，前端查到显示实际值，查不到显示 `—`。check 节点后调用写接口更新。

## 现状

latency 写 `nodes` 表三列 `tcp_latency` / `curl_latency` / `last_check_at`：

- **写**：`db/node.py:update_latency(node_id, tcp, curl, check_time)`，5 处调用
  - `routes/api_nodes.py:39`（手动 check）
  - `services/service_manager.py:176 / 209 / 546 / 590`（failover 切节点 / 扫描 / health daemon / phase3）——**均在不启动的 health-daemon 路径，后续整文件重写，本次不迁移**
- **读**：不是独立查询，latency 跟着 node 行走
  - `db/node.py` 的 `list_all` / `list_by_sub` / `get_by_id` / `list_grouped` 都是 `SELECT *`，三列随行带出
  - `db/outbound.py:get_pool_nodes` JOIN 里显式 `SELECT n.tcp_latency, n.curl_latency`
- **序列化**：`api_nodes.py` 的 `dict(n)`、`api_outbounds.py` 的 `dict(p)` 直接把列输出给前端

## 落点：`app/utils/latency.py`

放在 utils 下，对标现有 `port.py` / `logger.py` 先例：

- `logger.py` 已是「内存 deque + 锁 + 查询接口（`get_logs`）」的模块级单例，latency 同构（内存 dict + 锁 + `get_latency`）
- `port.py` 同样是「带内存状态（游标）+ 查询/分配接口」的底层工具
- 依赖：`latency.py` 只依赖 `app.utils.schemas.CheckResult`（utils 内部依赖），比 port/logger 还轻，不引入向外的边。依赖方向仍单向 `routes/checker → utils → settings`，无环

### 存储：内存 dict + 互斥锁

```python
# app/utils/latency.py
import threading
from app.utils.schemas import CheckResult

_lock = threading.Lock()   # 互斥锁（非队列）：写是纳秒级赋值，last-write-wins 即可
_latency = {}  # {node_id: CheckResult}
```

存完整 `CheckResult`（读写都用它），不关心前端字段名。

### 两个接口（入参均为 node id）

```python
def get_latency(node_id) -> CheckResult | None:
    """返回该节点最近一次 CheckResult；从未检查过则返回 None。"""

def update_latency(node_id, result: CheckResult) -> None:
    """存储（或覆盖）某节点的 CheckResult。"""
```

实现：

```python
def get_latency(node_id):
    with _lock:
        return _latency.get(node_id)

def update_latency(node_id, result):
    with _lock:
        _latency[node_id] = result
```

**字段由调用方自选**：`latency.py` 只做「node_id → CheckResult」的 KV 缓存；调用方（序列化处）决定取哪些字段、映射成什么前端字段名。

**接口是单结点**：50 个节点的读 = 50 次 `dict.get`（微秒级），跟 JSON 序列化 / 网络 I/O 比可忽略；无需批量 `node_id_list` 入参，上层加循环即可。

### `utils/__init__.py` 导出

```python
from .latency import get_latency, update_latency
```

调用方统一 `from app.utils import get_latency, update_latency`。

## 迁移：schema v2 删列

SQLite 3.35+ 支持 `DROP COLUMN`（本项目 3.37.2），无需重建表：

- `db/database.py`：`SCHEMA_VERSION = 2`
- `init_db()` 加 `if current < 2: _migrate_v2(db)`，`_migrate_v2` 执行
  ```sql
  ALTER TABLE nodes DROP COLUMN tcp_latency;
  ALTER TABLE nodes DROP COLUMN curl_latency;
  ALTER TABLE nodes DROP COLUMN last_check_at;
  ```
- `_create_v1` 保持历史定义不动；全新 DB 走 create v1 → migrate v2，语义正确。

## db 层全删

| 文件 | 改动 |
|------|------|
| `app/db/node.py` | 删 `update_latency` 函数；`update()` 的 `allowed` 去掉 `tcp_latency`/`curl_latency`/`last_check_at`；docstring 删「deprecated latency」段落 |
| `app/db/outbound.py` | `get_pool_nodes` 的 SELECT 去掉 `n.tcp_latency, n.curl_latency` |

> ⚠️ `db/node.py` 删掉 `update_latency` 后，`service_manager.py:17` 的
> `from app.db.node import get_by_id as get_node, update_latency` 会 import 失败。
> 故 `service_manager.py` **必须至少改这一行 import**（去掉 `update_latency`）。
> 其 4 处 daemon 内的 `update_latency(...)` 调用属死代码（daemon 已禁用不执行、
> 后续整文件重写），本次不迁移、保留不动。

## 序列化 merge（调用方自选字段）

latency 不再来自 DB 行，API 边界查内存、调用方把 `CheckResult` 字段映射为前端字段名：

| 文件 | 位置 | 改动 |
|------|------|------|
| `app/routes/api_nodes.py` | `list_nodes` / `list_nodes_grouped` / `list_nodes_by_sub` | 每个 `dict(n)` 后：`lat = get_latency(n['id'])`，`d['tcp_latency'] = lat.tcp_latency_ms if lat else None`，`d['curl_latency'] = lat.url_latency_ms if lat else None` |
| `app/routes/api_outbounds.py` | `list_outbounds` | pool 条目 `dict(p)` 后按 `p['node_id']` 查内存、同上映射 |

> 映射关系（调用方选字段）：`CheckResult.tcp_latency_ms` → 前端 `tcp_latency`，`CheckResult.url_latency_ms` → 前端 `curl_latency`；`success`/`http_code`/`error` 不选。无记录时 `lat is None` → 输出 `null`，前端 `!== null` 判断已适配（显示 `—`）。**前端零改动。**

## 写接口替换

只有 `api_nodes.py` 一处迁移（service_manager 不迁移）：

```python
# routes/api_nodes.py — res 已是 CheckResult，直接传
update_latency(nd['id'], res)
```

import 从 `from app.db.node import update_latency` 改为 `from app.utils import update_latency`。

## 实施顺序

1. 新建 `app/utils/latency.py`（读 `CheckResult|None`、写 `CheckResult`）
2. `utils/__init__.py` 导出 `get_latency` / `update_latency`
3. `db/database.py` schema v2 迁移删列
4. `db/node.py` / `db/outbound.py` 移除 latency 读写
5. `service_manager.py:17` import 去掉 `update_latency`（唯一必改点，其余不动）
6. `api_nodes.py` / `api_outbounds.py` 序列化 merge + 写接口改传 CheckResult
7. 验证

## 验证

```bash
# 迁移：旧库启动后三列消失
python3 -c "import sqlite3; c=sqlite3.connect('data/proxyhub.db'); print([r[1] for r in c.execute('PRAGMA table_info(nodes)')])"

# 读无记录返回 None、写后返回 CheckResult
python3 -c "from app.utils import get_latency, update_latency, CheckResult; print(get_latency(999)); update_latency(999, CheckResult(True, 12, 34, '204', '')); print(get_latency(999))"

# API 序列化：未检查节点字段为 null（前端显示 —）
python3 -c "from app.utils import get_latency; lat=get_latency(1); print({'tcp_latency': lat.tcp_latency_ms if lat else None, 'curl_latency': lat.url_latency_ms if lat else None})"

# 全应用 import 冒烟（确认 service_manager import 不崩）
python3 -c "import app.routes"
```

## 边界（不做）

- 不做持久化：app 重启 latency 清空是预期行为（前端显示 `—`）。
- 不做读接口的批量/缓存优化：单点 `get_latency(id)` 足够，节点数 ≤50。
- 不改前端：`!== null` 判断已兼容内存的 None。
- 不迁移 `service_manager.py` 的 latency 逻辑（daemon 已禁用 + 后续整文件重写），仅去掉失效 import。
