# ProxyHub v2 — 项目进度总览

> Archive: historical progress snapshot; not the current implementation status.

> 最后更新：2026-08-21
> 总代码量：4716 行（app/ + test/），41 个 API 端点，112 个测试

> ⚠️ 本文是 2026-08-21 的阶段进度快照，checker、认证和前端等“待实现”描述已不再代表当前代码。2026-08-24 的实际审查结果见 [known-issues.md](../backlog/known-issues.md) 和 [architecture-improvements.md](../backlog/architecture-improvements.md)。

## 1. 后端能力完成度

| 层 | 模块 | 状态 | 说明 |
|----|----|----|----|
| 设置 | `app/settings.py` | ✅ | 常量 + setting.json 持久化 |
| 数据库 | `app/db/` | ✅ | 7 表 + CRUD + 外键 + 反向引用查询 |
| 工具 | `app/utils.py` + `app/logger.py` | ✅ | common / validators / latency / logger |
| 订阅解析 | `app/parser/` | ✅ | URI 列表 + Clash YAML，6 协议，一协议一文件 |
| 订阅业务 | `app/services.refresh_subscription` | ✅ | fetch → parse → apply_node_diff → 更新元数据 |
| 引擎层 | `app/singbox/` | ✅ | protocol / config / process / upgrade / clash（5 模块） |
| sing-box 编排 | `app/services.apply_config` + start/stop/restart | ✅ | DB → config.json → 进程控制 |
| service 控制 | `app/services.start/stop/switch_service` | ✅ | selector 切换（v2 核心状态模型） |
| 路由层 | `app/routes.py` | ✅ | 41 个 /api/* 端点（CRUD + 进程 + service + 升级 + 设置） |
| Flask 工厂 | `app/__init__.py` | ✅ | create_app + 蓝图注册 + init_db |

## 2. 待实现功能

### 2.1 健康检查（checker）— 后端核心闭环

v2 检查机制两段式（[设计文档](design.md) §7）：

- **TCP 预筛**：Python socket 直连 `address:port`，取握手延迟
- **URL 测速**：调 `clash.get_delay(tag, url, timeout)`
- 两段串联：tcp 失败 → 跳过 url → 写 `CheckResult` 到内存 store

```
节点列表 → tcp_check(addr, port, timeout)
  ├─ 失败 → CheckResult(tcp=-1, url=-1, error='tcp: ...')
  └─ 成功 → clash.get_delay(tag, url, timeout)
       ├─ 失败 → CheckResult(tcp=N, url=-1, error='clash_api: ...')
       └─ 成功 → CheckResult(tcp=N, url=M, error='')
```

**输出**：写入 `app.utils.get_latency(node_id)` / `update_latency(node_id, result)` 内存 store。

**CheckResult 结构**（[routes.md §3.6](routes.md#36-apputilspy--checkresult-重构)）：
```python
@dataclass
class CheckResult:
    tcp_latency_ms: int    # -1 = 失败
    url_latency_ms: int    # -1 = 失败/未测
    error: str             # 失败原因（成功则 ''）
```

**前置**：`clash.get_delay`（✅ 已实现）。

### 2.2 调度（scheduler）— 自动切换

基于 checker 的结果做自动 failover：

- **正常模式**：按 `check_interval_normal`(240s) 周期检查
- **failover 模式**：当前节点不可用 → 缩短为 `check_interval_failover`(30s)
- **切换逻辑**：`clash.select_proxy(group_tag, next_node_tag)`
- **pool 排序**：priority ASC，failover 按序选下一个健康节点

```
scheduler 周期:
  1. 遍历所有 service → outbound → pool nodes
  2. 每个 node 调 checker 检测
  3. 当前节点 url_latency == -1（不可用）？
     ├─ 是 → 找 pool 中下一个 url_latency != -1 的节点 → select_proxy 切换
     └─ 否 → 保持
  4. 等待 interval → 回到 1
```

**前置**：checker（§2.1）。

### 2.3 认证

- `auth_required` 装饰器（routes/__init__.py 或单独 auth 模块）
- `session['authenticated']` 管理
- `web_password` 为空 → 跳过认证（[settings.md](settings.md) 默认值 `''`）
- `app.secret_key` 设置（当前未设）
- 登录页 `GET/POST /login`（唯一需要前端模板的路由）

v1 设计（§5.1）：
```
请求 → auth_required 装饰器
  ├─ web_password 为空 → 放行
  ├─ session['authenticated'] = True → 放行
  ├─ API 路由 → 返回 401 JSON
  └─ 页面路由 → 重定向 /login
```

### 2.4 前端

模板 + CSS/JS 全部内联进 [base.html](../../templates/base.html)（[structure.md](structure.md) 原则：无 static/，无构建步骤）。

**页面清单**（v1 §11）：
| 页面 | 路由 | 功能 |
|------|------|------|
| login | `GET/POST /login` | 用户名密码登录 |
| dashboard | `GET /` | 统计卡片 + 服务列表 + 状态栏 |
| subscriptions | `GET /subscriptions` | 订阅卡片 + 流量 + 关键字编辑 |
| nodes | `GET /nodes` | 按订阅分组折叠列表 + 延迟检测 |
| inbounds | `GET /inbounds` | 表格式入站管理 |
| outbounds | `GET /outbounds` | 卡片式出站 + 节点池管理 |
| settings | `GET /settings` | 6 个 section（二进制/检查/系统/危险区） |

**设计规范**（v1 §11.1）：色彩/字体/间距/按钮/卡片/模态框体系已详细定义。

**全局 JS**：`toggleLog()` / `addLog()` / `fetchLogs()` / `escapeHtml()` / `checkBinsStatus()`。

### 2.5 测试补全

| 测试文件 | 覆盖模块 | 状态 |
|----------|---------|------|
| `test_settings.py` | settings.py | ✅ |
| `test_protocol.py` | singbox/protocol.py | ✅ |
| `test_config.py` | singbox/config.py | ✅ |
| `test_process.py` | singbox/process.py | ✅ |
| `test_upgrade.py` | singbox/upgrade.py | ✅ |
| `test_logger.py` | logger.py | ✅ |
| `test_parser.py` | parser/ (URI + YAML) | ✅ 28 测试 |
| — | db/ (7 文件) | ❌ 无测试 |
| — | routes.py | ❌ 无测试 |
| — | services.py | ❌ 无测试 |
| — | singbox/clash.py | ❌ 无测试 |

### 2.6 Web 日志 API（可选）

- `GET /api/logs?since=N`（v1 §4.10 / §17）
- 需要内存日志收集器（`WebLogger`，deque(maxlen=500) + stdout/stderr 拦截）
- 前端底部日志面板依赖这个 API
- 现有 `app/logger.py` 只落文件，不提供 Web 实时读取

## 3. 推荐实现顺序

```
Phase 1: checker + scheduler   ← 后端核心闭环
         （订阅→节点→检查→自动切换，端到端自动化）

Phase 2: 认证                  ← 安全底线
         （裸 API 不上生产）

Phase 3: 前端                  ← 用户可见价值最大
         （base.html + 6 页面，纯 HTML/CSS/JS）

Phase 4: 测试补全              ← 质量保障
         （db + routes + services + clash）

Phase 5: Web 日志 API          ← 锦上添花
         （前端日志面板，优先级最低）
```

**Phase 1 完成后的闭环**：
```
订阅 URL → 拉取+解析 → 入库 → 生成 config → 启动 sing-box
    ↓                                              ↓
  刷新更新                                    健康检查
                                                    ↓
                                              自动 failover 切换
```

## 4. 文件结构总览

```
app/
├── __init__.py          # create_app() 工厂
├── settings.py          # 常量 + setting.json 持久化
├── logger.py            # 文件日志
├── utils.py             # common + validators + latency + CheckResult
├── routes.py            # Flask Blueprint（41 端点）
├── services.py          # 业务编排（订阅 + sing-box + service 控制）
├── db/                  # 数据层（7 表）
├── singbox/             # 引擎层（protocol / config / process / upgrade / clash）
└── parser/              # 订阅解析（6 协议 + Clash YAML）

templates/base.html      # 单页模板（占位）
test/                    # 112 测试
docs/                    # 11 个设计文档
data/                    # 运行时数据（gitignore）
logs/                    # 日志（gitignore）
```
