# 路由层 + sing-box 编排 + CheckResult 重构实现计划

> Archive: historical implementation plan; not the current implementation status.

> 层级：Web/路由层 + 服务层 + 工具层。承接 [顶层设计](design.md) §5 的 Web/路由层 + 进程管理层细化。
> 状态：⏳ 待确认。

## 1. 背景

"从订阅到启动 sing-box"这条链目前断在第 4 环：当时的 `app/services.py` 只做了订阅刷新，没有函数把 DB 状态组装成 `db_state` → `build_config` → `write_config` → `process.start/restart` 串起来。[config.py:101](../../app/singbox/config.py#L101) docstring 写着"db_state 由调用方组装"但这个调用方不存在。

用户决定把第 4 环（sing-box 编排）和 routes 一起做——routes 需要 start/stop/restart/is_running 接口暴露给前端。本计划实现 `app/routes.py`（Flask Blueprint）+ 在 `app/services.py` 补 sing-box 编排函数 + `app/singbox/clash.py` 实现 clash_api 客户端（start/stop 依赖查询当前状态）+ `CheckResult` 重构（v2 检查机制变了，原结构已不适用）。`create_app()` 接上蓝图注册 + DB 初始化。

不做前端模板（[base.html](../../templates/base.html) 仍是占位），不做认证，不做节点/订阅 CRUD 页面——本轮只把"进程控制 + 配置应用"的后端 API 跑通。

## 2. 各环节状态回顾

| 环节 | 实现 | 状态 |
|----|----|----|
| 1. 拉取订阅 + 解析 + 入库 | `services.refresh_subscription` | ✅ |
| 2. DB → config.json 生成 | `singbox.config.build_config` + `write_config` | ✅ 纯函数 |
| 3. 启动 sing-box 进程 | `singbox.process.start/restart` | ✅ |
| **4. 把 2+3 串起来的编排** | **无** | ❌ **本轮补** |
| 5. clash_api 测速/切换 | `singbox.clash` | ⚠️ 全是 NotImplementedError，**本轮补** |
| 6. Web 路由 | `routes.py` / `create_app` | ❌ 不存在，**本轮补** |
| 7. CheckResult 数据结构 | `utils.CheckResult` | ⚠️ 5 字段含废弃的 `http_code`/`success`，**本轮重构** |

## 3. 改动清单

### 3.1 `app/db/outbound.py` — 补 `list_all_pool_entries()`

`build_config` 需要 `outbound_nodes`（全表 pool 条目，含 `outbound_id`/`node_id`/`priority`）。现有 `get_pool_nodes(outbound_id)` 是按单个 outbound 查询（还 JOIN 了 node 详情），不适用。补一个：

```python
def list_all_pool_entries():
    """Return all outbound_nodes rows ordered by outbound_id, priority."""
    db = get_db()
    return db.execute(
        'SELECT outbound_id, node_id, priority FROM outbound_nodes '
        'ORDER BY outbound_id, priority ASC'
    ).fetchall()
```

返回 `sqlite3.Row`，字段名与 [config.py](../../app/singbox/config.py) `_build_selectors` 读取的 `e['outbound_id']`/`e['node_id']`/`e['priority']` 对齐。

### 3.2 `app/services.py` — 补 sing-box 编排

在现有订阅函数下方加 sing-box 生命周期编排：

```python
def apply_config():
    """DB → config.json（不碰进程）。供 apply_and_start / routes 复用。"""

def start_singbox():
    """应用配置 + 启动 sing-box（若已运行则 restart）。返回 {success, message, pid}。"""

def stop_singbox():
    """停止 sing-box。委托 singbox.process.stop()。"""

def restart_singbox():
    """重新生成 config + restart。"""

def get_status():
    """sing-box 是否运行 + 版本 + pid（若运行）。"""
```

- `apply_config` 组装 `db_state`（nodes / inbounds / outbounds / outbound_nodes / services，全部从 `app.db.*` 的 `list_all()` / `list_all_pool_entries()` 取），调 `singbox.build_config` + `singbox.write_config`
- `start_singbox` 先 `apply_config` 再调 `singbox.process.start`；若 `is_running()` 则改调 `restart`
- 日志用 `log.info(msg)`（v2 风格）

### 3.3 `app/singbox/clash.py` — 实现 clash_api 客户端

用 `urllib.request` 调 `127.0.0.1:{clash_api_port}` 的 clash_api。base/port 从 `settings.get_setting('clash_api_port')` 取，URL 编码节点 tag。

```python
def get_delay(node_name, url, timeout) -> dict:
    """GET /proxies/{node}/delay?url=...&timeout=... → {"delay": N} 或 {"message": ...}"""

def get_proxies() -> dict:
    """GET /proxies → 全量 proxy 映射（含每个 selector 的 now）"""

def select_proxy(group, node) -> bool:
    """PUT /proxies/{group} body {"name": node} → 切 selector 当前节点"""

def get_proxy_now(group) -> str | None:
    """GET /proxies/{group} → 取 now（当前选中节点 tag）"""
```

- 超时用 `settings.get_setting('curl_timeout')`
- `select_proxy` 返回 bool，HTTP 非 2xx → False
- 失败不抛异常，返回带 `error` 的 dict / False，调用方（scheduler/checker）决定如何处理
- clash_api 无 secret（[config.py](../../app/singbox/config.py) 生成时 `secret: ''`），请求不带 Authorization

### 3.4 `app/routes.py` — Flask Blueprint（本轮只做进程控制 + 状态）

```python
from flask import Blueprint, jsonify, request
from app import services

bp = Blueprint('api', __name__)

@bp.route('/api/status', methods=['GET'])
def api_status():
    """sing-box 运行状态 + 版本。"""

@bp.route('/api/start', methods=['POST'])
def api_start():
    """应用配置 + 启动 sing-box。"""

@bp.route('/api/stop', methods=['POST'])
def api_stop():
    """停止 sing-box。"""

@bp.route('/api/restart', methods=['POST'])
def api_restart():
    """重新生成 config + restart。"""
```

- 统一返回 `jsonify({success, message, ...})`
- 不做认证（后续 Web 层再加 `auth_required` 装饰器，[design.md](design.md) §2 核心决策已留口）
- 不做节点/订阅/出站 CRUD 路由——本轮聚焦"start/stop/restart/is_running"，其余等前端一起做

### 3.5 `app/__init__.py` — `create_app()` 接上蓝图 + DB 初始化

```python
def create_app() -> Flask:
    app = Flask(__name__)
    from app.routes import bp
    app.register_blueprint(bp)
    from app.db.database import init_db
    init_db()
    return app
```

### 3.6 `app/utils.py` — `CheckResult` 重构

v2 检查机制是两段式（tcp 预筛 + clash_api `/delay`），原结构含 v1 残留字段已不适用。按讨论定稿精简：

**原结构（5 字段，含废弃字段）：**
```python
@dataclass
class CheckResult:
    success: bool
    tcp_latency_ms: int       # TCP handshake latency (-1 if failed)
    url_latency_ms: int       # URL latency (-1 if not done)
    http_code: str            # URL HTTP code ("0" if not done)  ← 删
    error: str
```

**新结构（3 字段）：**
```python
@dataclass
class CheckResult:
    tcp_latency_ms: int    # TCP 握手延迟（-1 = 失败）
    url_latency_ms: int    # URL 测速延迟（-1 = 失败/未测）
    error: str             # 失败原因（成功则 ''）—— 日志/排查用
```

**改动与理由：**

| 字段 | 处置 | 理由 |
|----|----|----|
| `success: bool` | 删 | `success` 语义模糊（tcp 成功 url 失败算成功吗），且可用 `url_latency_ms != -1` 推导（url 测通才"成功"） |
| `http_code: str` | 删 | [design.md](design.md) §6 + [refer.md](refer.md) §7 已定要砍，clash_api `/delay` 不返回状态码 |
| `is_available: bool` | 不加 | 可由 `url_latency_ms != -1` 推导，调用方一行判断，不冗余存储 |
| `checked_at` | 不加 | 内存 store 是 last-write-wins，时间戳存了也不持久有意义；"多久前"靠轮询间隔 + 日志时间戳 |
| `error: str` | 留 | 调度层/重试逻辑拿到 result 时能看上次失败原因，成本就一个字符串字段 |

**三种状态表达（无 `success`/`status`/`is_available`）：**

| tcp_latency_ms | url_latency_ms | 含义 | error |
|----|----|----|----|
| -1 | -1 | tcp 死，跳过 url | "tcp: Connection refused" |
| 142 | -1 | tcp 通，url 测速失败 | "clash_api: timeout" |
| 142 | 356 | 全通 | '' |

调用方判断可用性：`url_latency_ms != -1`。

## 4. 依赖方向

```
routes.py ──▶ services.py ──▶ db.* / singbox.*
                    │
                    ├── db.node / db.inbound / db.outbound / db.service（读 DB 组装 db_state）
                    ├── singbox.config（build_config + write_config）
                    ├── singbox.process（start / stop / restart / is_running）
                    └── singbox.upgrade（get_version，状态查询用）

clash.py（被未来 checker / scheduler 消费，本轮不写消费者）
```

## 5. 不做的事

- 不做前端模板 / CSS / JS（[base.html](../../templates/base.html) 保持占位）
- 不做认证（routes 暂时裸暴露，后续加 `auth_required`）
- 不做节点/订阅/出站/服务的 CRUD 路由（等前端页面一起做）
- 不做 checker（tcp_check + url_check）/ scheduler（failover/fallback）——clash.py 实现后它们才有原料，但本轮不写
- 不碰现有 `test/`

## 6. 验证

1. **import 链**：`venv/bin/python -c "from app import create_app; app = create_app(); print(app.url_map)"`
2. **clash.py 单元**：sing-box 未运行时 `get_proxies()` 应返回 `{'error': ...}` 而非抛异常
3. **端到端**（需 sing-box 二进制存在）：
   - `services.apply_config()` → 检查 `data/config.json` 生成
   - `services.start_singbox()` → `is_running()` True
   - `curl -X POST http://localhost:8080/api/start` → `{"success": true}`
   - `curl http://localhost:8080/api/status` → 运行中 + 版本
   - `services.get_delay('n1', test_url, 5000)` → 真实延迟（若节点可达）
   - `curl -X POST http://localhost:8080/api/stop` → 停止
4. **现有测试不回归**：`venv/bin/python -m unittest discover -s test -q`
