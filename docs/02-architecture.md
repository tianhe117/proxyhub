# ProxyHub 软件架构设计

> 文档版本：v1.0  
> 文档状态：已冻结

> 更新日期：2026-09-04

> 适用范围：ProxyHub 第一版  
> 上游文档：`docs/01-requirements.md`

---

# 1. 文档目的

本文定义 ProxyHub 第一版的软件总体架构，包括：

- 技术栈；
- 进程模型；
- 模块划分；
- 模块职责；
- 模块依赖关系；
- 数据与状态归属；
- 并发模型；
- sing-box 集成边界；
- Web 与业务层边界；
- 项目目录结构。

本文回答：

> ProxyHub 整体如何组织，各模块分别负责什么，以及模块之间如何协作。

本文不定义：

- SQLite 具体表结构；
- 字段、索引和外键；
- Node 协议字段矩阵；
- sing-box 配置字段映射；
- AUTO 详细控制流程；
- HTTP API 路径和数据格式；
- Web 页面布局；
- 测试用例；
- 部署命令。

上述内容由后续专题设计文档定义。

---

# 2. 架构原则

## 2.1 简单优先

ProxyHub 是单人使用、自行部署的本地代理管理工具。

第一版优先保证：

- 功能明确；
- 行为确定；
- 模块边界清晰；
- 容易测试；
- 容易排错；
- 容易维护；
- 容易由 AI 辅助开发。

不为未来可能出现的规模提前增加复杂基础设施。

---

## 2.2 单体应用

ProxyHub 第一版采用单体应用架构。

所有 ProxyHub 业务逻辑运行在一个 Python 进程内，包括：

- Flask Web；
- Internal API；
- Service；
- Runtime Controller；
- AUTO 控制；
- Node 健康检测；
- SQLite 数据访问；
- sing-box 管理。

sing-box 作为独立子进程运行。

整体模型：

```text
ProxyHub Python Process
│
├── Flask Web / API
├── Business Services
├── Runtime Controller
├── Node Checker
├── SQLite Access
│
└── sing-box subprocess
```

---

## 2.3 模块化而非服务化

系统按职责划分 Python 模块。

模块之间通过普通 Python 函数和对象直接调用。

第一版不引入：

- 微服务；
- RPC；
- MQ；
- Event Bus；
- Redis；
- Celery；
- 独立 Worker；
- 分布式锁。

---

## 2.4 明确状态来源

系统状态分为三类：

```text
业务配置        → SQLite
应用 Settings   → settings.json
运行时状态      → Python 内存
```

sing-box 配置文件属于派生数据，不是业务数据源。

原则上：

> 一个状态只存在一个权威来源。

避免多份状态之间的同步问题。

---

# 3. 技术栈

第一版采用以下技术栈：

| 能力 | 技术 |
|---|---|
| 开发语言 | Python 3 |
| Web Framework | Flask |
| HTML Template | Jinja2 |
| 数据库 | SQLite |
| 数据库访问 | Python `sqlite3` |
| HTTP Client | `requests` |
| TCP 检测 | Python `socket` |
| 并发 | `threading` / `concurrent.futures` |
| sing-box 进程管理 | `subprocess` |
| 配置文件 | JSON |
| 日志 | Python `logging` |
| 测试 | pytest |

核心第三方依赖保持最少：

```text
Flask
requests
pytest
```

数据库直接使用 Python 标准库：

```text
sqlite3
```

第一版不使用 ORM。

---

# 4. 总体架构

系统总体结构如下：

```text
                    Browser
                       │
                       │ HTTP
                       ▼
                ┌─────────────┐
                │ Flask Web   │
                │ / API       │
                └──────┬──────┘
                       │
                       ▼
                ┌─────────────┐
                │  Services   │
                │ 业务用例编排 │
                └───┬─────┬───┘
                    │     │
             ┌──────┘     └─────────┐
             ▼                      ▼
       ┌──────────┐           ┌───────────┐
       │ DB Layer │           │  Runtime  │
       │ SQLite   │           │ Controller│
       └──────────┘           └─────┬─────┘
                                    │
                          ┌─────────┼─────────┐
                          ▼         ▼         ▼
                       Checker   sing-box   Runtime
                                  Layer      State
                                    │
                      ┌─────────────┼─────────────┐
                      ▼             ▼             ▼
                 config.json    subprocess    Clash API
                                    │
                                    ▼
                                sing-box
```

Subscription Parser 是独立模块：

```text
Subscription Content
        ↓
      Parser
        ↓
标准 Node 数据
        ↓
     Service
        ↓
      SQLite
```

---

# 5. 进程模型

## 5.1 单 ProxyHub 进程

第一版只运行一个 ProxyHub Python 进程。

该进程内部包含：

```text
ProxyHub Process
│
├── Flask Request Threads
│
└── Runtime Controller Thread
```

允许 Flask 使用多线程处理 HTTP 请求。

但不允许运行多个应用进程。

因此：

```text
单进程
+
多线程
```

是第一版基本运行模型。

---

## 5.2 单 Worker

部署环境必须保持单 Worker。

不得同时启动多个 ProxyHub Python Worker。

原因是以下状态均保存在进程内：

- management state；
- Node Health；
- AUTO Runtime State；
- Runtime Control Lock；
- Runtime Controller。

多个 Worker 会产生多份独立运行状态，因此第一版不支持。

---

## 5.3 sing-box 子进程

ProxyHub 最多管理一个 sing-box 子进程。

关系：

```text
ProxyHub Process
        │
        └── sing-box Process
```

ProxyHub 负责：

- 检测二进制；
- 读取版本；
- 下载；
- 升级；
- 启动；
- 停止；
- Restart；
- 判断进程是否仍然存在。

---

# 6. 后台控制模型

ProxyHub 运行一个唯一 Runtime Controller Thread。

其核心职责包括：

```text
Process Watchdog
+
AUTO Control
```

基本流程：

```text
Control Cycle
      ↓
检查 sing-box process
      ↓
执行 AUTO Control
      ↓
等待下一周期
```

所有 Routed AUTO 都由该控制线程顺序处理。

不为每个 AUTO 创建独立线程。

---

## 6.1 stopped 状态

Runtime Controller Thread 可以一直存在。

当：

```text
management_state = stopped
```

时：

- 不执行 sing-box Process Watchdog；
- 不执行 AUTO Control；
- 等待下一周期或状态变化。

这样无需频繁创建和销毁后台线程。

---

# 7. 并发模型

第一版主要存在以下并发：

```text
Flask Request Threads
Runtime Controller Thread
Node Detection Worker Threads
```

其中 Node 批量检测使用：

```python
concurrent.futures.ThreadPoolExecutor
```

进行有限并发。

系统不建立通用异步任务平台。

---

# 8. Runtime Control Lock

系统创建唯一一把进程内运行控制锁：

```text
runtime_control_lock
```

可以使用：

```python
threading.Lock
```

---

## 8.1 需要持锁的操作

所有可能改变 sing-box 运行结构、生命周期或关键运行状态的操作统一串行执行。

包括：

- Start；
- Stop；
- Restart；
- 结构配置写操作；
- priority 在线重排；
- MANUAL Current Node 在线切换；
- sing-box 下载；
- sing-box 升级替换；
- Runtime Controller 完整控制周期；
- 后台故障恢复 Restart。

---

## 8.2 不持锁的操作

以下操作无需取得 Runtime Control Lock：

- Settings 保存；
- Subscription Metadata Refresh；
- 人工 Node 检测；
- 普通只读查询。

这些操作不改变 sing-box 当前结构配置或运行生命周期。

结构配置写与 priority 在线重排共用同一把锁，但状态门槛不同：

```text
结构配置写
→ Acquire runtime_control_lock
→ 检查 management_state == stopped

priority 在线重排
→ Acquire runtime_control_lock
→ 不检查 stopped
→ running / stopped 均可执行
```

---

## 8.3 Restart

Restart 在一次 Lock 生命周期内完成：

```text
Acquire Lock
    ↓
Stop
    ↓
Start
    ↓
Release Lock
```

Stop 和 Start 的底层实现应支持：

```text
调用方已经持锁
```

的内部调用方式。

避免 Restart 内部重复取得同一把锁。

---

# 9. 状态与数据归属

ProxyHub 明确区分：

```text
Persistent Business State
Application Settings
Runtime State
Generated Files
```

---

# 10. 业务数据

业务数据保存在：

```text
data/proxyhub.db
```

主要包括：

- Subscription；
- Node；
- Inbound；
- MANUAL Outbound；
- AUTO Outbound；
- Route；
- Outbound Node Pool；
- priority；
- MANUAL Current Node；
- AUTO Fallback Node。

DIRECT 是系统内置对象，不作为普通 Outbound 数据记录保存。

数据库具体设计由：

```text
docs/03-data-model.md
```

定义。

---

# 11. Settings

应用设置保存在：

```text
data/settings.json
```

Settings 独立于 SQLite。

应用启动时：

```text
读取 settings.json
        ↓
补齐缺失字段
        ↓
完整校验
        ↓
生成内存 Settings
```

Web 页面保存设置时：

```text
校验
 ↓
写临时文件
 ↓
原子替换 settings.json
 ↓
更新内存 Settings
```

运行任务在开始时取得当前 Settings。

任务执行过程中 Settings 即使发生修改，该任务也继续使用开始时取得的配置。

---

# 12. Runtime State

运行时数据只保存在 Python 内存中。

包括：

## 12.1 系统运行状态

```text
management_state
sing-box process state
```

---

## 12.2 Node Health

```text
available / unavailable / unknown
tcp_delay
url_delay
last_checked
failure_reason
```

---

## 12.3 AUTO Runtime State

例如：

```text
Current Node
Failure Count
Fallback Started Time
Priority Recovery Timer
```

这些数据不写入 SQLite。

Start / Restart 后根据 Requirements 重新初始化。

---

# 13. 生成文件

以下文件属于派生数据：

```text
data/config.json
data/config.previous.json
```

业务配置的 Source of Truth 始终是：

```text
SQLite
+
settings.json
```

不得：

- 从 config.json 恢复业务对象；
- 从 sing-box 配置反向更新 SQLite；
- 将 config.json 当作数据库使用。

---

# 14. Web 层

Web 层负责：

- Flask 页面；
- Internal API；
- Request 参数读取；
- Authentication；
- 调用 Service；
- 将业务结果转换成 HTTP Response。

主要入口：

```text
app/routes.py
```

第一版可以使用单 Blueprint。

---

## 14.1 Web 层禁止事项

Web 层不得直接：

- 执行 SQL；
- 修改 SQLite；
- 调用 subprocess；
- 调用 Clash API；
- 实现级联删除；
- 实现 Subscription diff；
- 实现 AUTO Control；
- 修改 Runtime State。

正确调用方式：

```text
HTTP
 ↓
Routes
 ↓
Service
```

---

# 15. Service 层

Service 层负责：

> 用户业务操作的完整编排。

目录：

```text
app/services/
```

建议结构：

```text
services/
├── __init__.py
├── subscription.py
├── node.py
├── inbound.py
├── outbound.py
├── route.py
└── system.py
```

---

## 15.1 Subscription Service

负责：

- 创建 Subscription；
- 修改 Subscription；
- 删除 Subscription；
- Subscription Metadata Refresh；
- Subscription Sync（同步订阅节点）；
- Filter / Exclude；
- diff；
- Preview；
- Confirm；
- 删除和同步产生的级联业务处理。

两项 Subscription 操作边界固定为：Metadata Refresh 不经过 Parser，只更新流量、有效期等元信息且不修改 Node；Sync 执行 Parser、Diff、Preview、Confirm 和 Node 更新。

---

## 15.2 Node Service

负责：

- 创建自建 Node；
- 修改 Node；
- 删除 Node；
- Node 删除影响分析；
- 人工 Node 检测请求。

---

## 15.3 Inbound Service

负责：

- Inbound CRUD；
- Route 引用关系检查；
- 删除影响处理。

---

## 15.4 Outbound Service

负责：

- MANUAL CRUD；
- AUTO CRUD；
- Node Pool；
- priority 查询与重排；
- priority 在线修改业务校验；
- priority 原子更新；
- MANUAL Current Node；
- AUTO Fallback Node；
- Outbound 类型转换；
- MANUAL 在线节点切换。

Outbound Service 必须保证 priority 重排提交的成员与当前 Node Pool 完全一致、提交顺序完整、最终 priority 连续且唯一，并在一个 SQLite transaction 中完成全部更新。

---

## 15.5 Route Service

负责：

- Route CRUD；
- Inbound 唯一引用规则；
- MANUAL / AUTO / DIRECT Outbound 选择；
- Route 删除和引用检查。

---

## 15.6 System Service

负责用户主动触发的系统操作：

```text
Start
Stop
Restart
sing-box Version
Download
Upgrade
```

实际底层操作委托给：

```text
runtime
singbox
```

---

# 16. Database 层

目录：

```text
app/db/
```

建议：

```text
db/
├── __init__.py
├── database.py
├── subscription.py
├── node.py
├── inbound.py
├── outbound.py
├── route.py
└── references.py
```

---

## 16.1 database.py

负责数据库基础能力：

- 建立连接；
- 初始化 schema；
- transaction；
- commit；
- rollback；
- SQLite PRAGMA 初始化。

不包含业务规则。

---

## 16.2 数据访问模块

各实体文件只处理对应数据对象。

例如：

```text
db/node.py
```

负责：

```text
get
list
insert
update
delete
```

数据库模块不负责决定：

- 删除 Node 后是否删除 Outbound；
- Current 如何替换；
- Fallback 如何替换；
- Route 是否应该级联删除。

这些属于 Service 层业务逻辑。

---

## 16.3 references.py

`references.py` 负责跨实体引用查询。

例如：

- Node 被哪些 Outbound 使用；
- Outbound 被哪些 Route 使用；
- Inbound 是否已存在 Route；
- 级联 Preview 所需引用关系。

它只提供数据。

不决定如何处理引用关系。

---

# 17. SQLite Connection 管理

SQLite Connection 不在线程之间共享。

原则：

```text
一个操作线程
→ 一个 SQLite Connection
```

不得依赖：

```python
check_same_thread=False
```

将一个 Connection 在多个线程之间长期共享。

---

## 17.1 多表事务

对于需要修改多个表的业务事务：

```text
Service
    ↓
创建 Connection
    ↓
BEGIN
    ↓
多个 DB Module 共用该 Connection
    ↓
COMMIT / ROLLBACK
```

例如：

```text
Subscription Sync Confirm
        ↓
BEGIN
        ↓
Subscription
Node
Outbound
Route
        ↓
COMMIT
```

Service 负责事务范围。

DB Module 负责具体 SQL。

---

# 18. Parser 层

目录：

```text
app/parser/
```

结构：

```text
parser/
├── __init__.py
├── base.py
├── ss.py
├── vmess.py
├── vless.py
├── trojan.py
└── hysteria2.py
```

第一版支持：

- Shadowsocks；
- VMess；
- VLESS；
- Trojan；
- Hysteria2。

---

## 18.1 Parser 职责

Parser 负责：

```text
Subscription / Share URI
        ↓
Decode
        ↓
协议识别
        ↓
字段解析
        ↓
标准 Node 数据
```

---

## 18.2 Parser 边界

Parser 不负责：

- SQLite；
- Subscription diff；
- Node 身份匹配；
- Service；
- sing-box 配置；
-健康检测；
- AUTO。

Parser 应尽可能实现为纯函数，方便独立测试。

---

# 19. sing-box 集成层

目录：

```text
app/singbox/
```

结构：

```text
singbox/
├── __init__.py
├── protocol.py
├── config.py
├── process.py
├── clash.py
└── upgrade.py
```

---

# 20. protocol.py

负责：

```text
ProxyHub Node Data
        ↓
sing-box Proxy Outbound Data
```

只负责协议字段转换。

原则上使用纯函数。

不得直接读取数据库。

---

# 21. config.py

负责根据已经取得的业务配置生成完整 sing-box 配置。

包括：

- Node Outbound；
- MANUAL selector；
- AUTO selector；
- DIRECT；
- Inbound；
- Route；
- Clash API。

调用关系：

```text
Service / Runtime
      ↓
读取 SQLite
      ↓
整理业务配置
      ↓
singbox.config
      ↓
完整 config dict
```

`config.py` 不直接访问 SQLite。

这样 Config Builder 可以独立测试。

Config Builder 不接收或解释 priority 的业务语义。priority 不生成到 sing-box 配置，也不通过 selector 成员顺序表达；它留在 ProxyHub Service 和 AUTO Control 层。Config Builder 只取得 Node、Node Pool 成员、MANUAL Current、AUTO Fallback、Routed 对象及其他实际生成配置所需数据。

运行配置按以下规则裁剪：所有合法全局 Node 均生成独立 remote outbound；只有被至少一条 Route 引用的 MANUAL/AUTO 和 Inbound 才生成对应运行对象；DIRECT 仅在至少一条 Route 使用时生成。

---

# 22. process.py

封装 sing-box 进程基础操作：

```text
check config
start process
stop process
wait process
is running
read version
```

它不负责：

- management state；
- AUTO；
- Runtime State；
- 用户权限；
- 是否允许 Start/Restart。

这些由 Service / Runtime 决定。

---

# 23. clash.py

封装 ProxyHub 使用的最小 Clash API 能力：

- URL Delay；
- 读取 Selector Current Node；
- Selector Switch；
- Clash API 可用性检测。

不实现完整 Clash API SDK。

---

# 24. upgrade.py

负责：

- 获取本地 sing-box 版本；
- 查询远程版本；
- 下载；
- 解压；
- 验证；
- 临时文件管理；
- 原子替换二进制。

具体 Release 策略和资产选择由：

```text
docs/04-singbox-design.md
```

定义。

---

# 25. Checker

文件：

```text
app/checker.py
```

统一负责 Node 健康检测。

基本模型：

```text
Node
 ↓
TCP Check
 ↓
URL Delay
 ↓
Health Result
```

结果至少包括：

```text
status
tcp_delay
url_delay
failure_reason
checked_at
```

Checker 不实现 AUTO 行为。

它只返回检测结果。

---

## 25.1 检测调用方

Checker 可以被：

```text
人工 Node 检测
AUTO Control
```

共同使用。

不同调用方使用相同的检测实现。

---

## 25.2 批量检测

批量检测通过：

```python
ThreadPoolExecutor
```

实现。

每次检测任务使用当前 Settings 中的：

```text
Max Concurrency
```

作为本次线程池并发限制。

系统不建立永久 Detection Worker Pool。

---

# 26. Runtime 层

目录：

```text
app/runtime/
```

结构：

```text
runtime/
├── __init__.py
├── state.py
├── controller.py
└── auto.py
```

---

# 27. runtime/state.py

负责保存所有 Runtime State。

主要包括：

```text
management_state
runtime_control_lock
Node Health
AUTO Runtime State
sing-box Process State
```

这里只保存状态。

不实现完整业务流程。

---

# 28. runtime/controller.py

负责：

- Runtime Controller Thread；
- Control Loop；
- Process Watchdog；
- Start；
- Stop；
- Restart；
- Runtime State Reset；
- Routed AUTO 调度。

基本控制周期：

```text
Acquire Runtime Control Lock
        ↓
Process Watchdog
        ↓
AUTO Control
        ↓
Release Lock
        ↓
Sleep
```

如果本周期触发 Restart，则结束当前周期。

---

# 29. runtime/auto.py

负责 AUTO 业务控制规则。

主要包括：

- Fallback Recovery；
- Current Candidate Check；
- failure count；
- Candidate → Fallback；
- Priority Recovery；
- Fallback Timeout。

AUTO 不创建独立线程。

所有 AUTO 都由 Runtime Controller 统一调用。

AUTO 执行需要基于 priority 的 Candidate 选择时，从业务数据层取得当前最新 priority。priority 不属于 AUTO Runtime State，不在 Start 时复制为长期内存状态；不为此增加 cache、runtime mirror、DB change event、watcher 或 event bus。

详细控制规则由：

```text
docs/05-runtime-control.md
```

定义。

---

# 30. Settings 模块

文件：

```text
app/settings.py
```

负责：

- Default Settings；
- 加载；
- 缺失字段补全；
- 完整校验；
- 内存 Settings；
- 页面保存；
- JSON 序列化；
- 临时文件；
- 原子替换。

Settings 不依赖 SQLite。

---

# 31. Authentication

文件：

```text
app/auth.py
```

负责：

- Username / Password 验证；
- Password Hash；
- Login；
- Logout；
- Flask Session；
- Authentication Decorator；
- Session 失效。

第一版只有一个本地管理账号。

不建立：

- User 表；
- Role；
- Permission；
- Token System。

认证配置保存在：

```text
settings.json
```

Session Secret 独立保存在：

```text
data/session.secret
```

---

# 32. Logging

文件：

```text
app/logger.py
```

负责：

- Logging 配置；
- File Handler；
- Formatter；
- 日志文件创建；
- 日志路径。

日志初始化必须由启动流程显式调用：

```python
configure_logging()
```

不得依靠 import 副作用创建日志文件。

---

## 32.1 敏感信息

以下内容不得以原文写入日志：

- Password；
- Token；
- UUID；
- Node Secret；
- Subscription URL；
- 分享 URI；
- 完整原始代理配置。

业务模块在记录日志前应避免产生敏感内容。

---

# 33. Utils

文件：

```text
app/utils.py
```

只保存无明确业务归属、无状态的公共辅助函数。

例如：

- 时间处理；
- 安全字符串处理；
- 少量 validator；
- 通用文件操作辅助。

具有明确业务含义的代码必须放在对应模块。

---

# 34. 模块依赖原则

总体依赖方向：

```text
routes
   ↓
services
   ↓
┌────────┬─────────┬─────────┬──────────┐
↓        ↓         ↓         ↓
db     parser    runtime   settings
                   ↓
             ┌─────┴─────┐
             ↓           ↓
          checker      singbox
```

Service 可以根据具体业务直接调用：

```text
db
parser
runtime
singbox
checker
settings
```

---

## 34.1 禁止反向依赖

禁止：

```text
db → service

parser → service

singbox → service

singbox → routes

runtime → routes

checker → auto
```

底层模块不得主动调用 Web 层。

---

# 35. 结构配置写入流程

所有结构配置修改统一采用：

```text
HTTP Request
      ↓
Route
      ↓
Service
      ↓
Acquire runtime_control_lock
      ↓
确认 management_state == stopped
      ↓
BEGIN SQLite Transaction
      ↓
业务校验
      ↓
写数据库
      ↓
COMMIT
      ↓
Release Lock
```

必须在取得 Lock 后再次检查：

```text
management_state
```

避免检查状态后、真正写库前发生 Start。

---

## 35.1 stopped 下只修改数据库

在 stopped 状态执行结构配置修改时：

```text
只修改 SQLite
```

不：

- 立即生成 config.json；
- 执行 sing-box check；
- 自动 Restart。

配置统一在下一次：

```text
Start / Restart
```

时重新生成。

---

## 35.2 priority 在线写入流程

priority 重排是 Outbound Service 的独立业务操作，不属于结构配置写：

```text
HTTP Request
      ↓
Route
      ↓
Outbound Service
      ↓
Acquire runtime_control_lock
      ↓
BEGIN SQLite Transaction
      ↓
读取并确认当前 Node Pool
      ↓
校验提交成员与现有成员完全一致
      ↓
按提交顺序重排 1...N priority
      ↓
COMMIT
      ↓
Release runtime_control_lock
```

该流程不要求 `management_state == stopped`，在 `running` 和 `stopped` 时均可执行；不生成 `config.json`，不执行 `sing-box check`，不调用 Clash API，不 Restart，也不直接修改 Runtime State。AUTO Controller 后续需要依据 Candidate priority 决策时读取数据库中的最新值。

---

# 36. Preview / Confirm

涉及级联影响的操作采用：

```text
Preview
→ Confirm
```

例如：

- Subscription Sync；
- Node 删除；
- Subscription 删除；
- 其他可能级联删除 Outbound / Route 的操作。

---

## 36.1 Preview

Preview 阶段：

```text
读取当前数据
     ↓
计算变化
     ↓
计算级联影响
     ↓
返回用户确认
```

不得修改数据库。

---

## 36.2 Confirm

Confirm 阶段：

```text
Acquire runtime_control_lock
      ↓
确认 stopped
      ↓
重新确认相关数据仍然有效
      ↓
BEGIN
      ↓
执行完整事务
      ↓
COMMIT
```

不得假设 Preview 后数据库一定没有变化。

具体数据一致性判断方式由：

```text
docs/03-data-model.md
```

定义。

---

# 37. sing-box 配置生成流程

实际需要启动 sing-box 时：

```text
读取最新 SQLite
      ↓
构造运行配置数据
      ↓
singbox.config
      ↓
生成临时 config
      ↓
sing-box check
      ↓
成功
      ↓
原子替换 config.json
      ↓
启动 sing-box
```

如果 check 失败：

- 不启动 sing-box；
- 不修改业务数据库；
- 保留错误信息供用户查看。

---

# 38. ProxyHub 启动流程

推荐启动顺序：

```text
run.py
  ↓
创建运行目录
  ↓
初始化 Logging
  ↓
加载并校验 settings.json
  ↓
初始化 SQLite
  ↓
初始化 Runtime State
  ↓
创建 Flask App
  ↓
根据 Requirements 判断是否自动启动 sing-box
  ↓
启动 Runtime Controller Thread
  ↓
启动 Web Server
```

如果：

- sing-box 未安装；
- 无 Route；
- config check 失败；
- sing-box Start 失败；

ProxyHub Web 仍然启动。

此时系统保持：

```text
management_state = stopped
```

---

# 39. Flask App Factory

文件：

```text
app/__init__.py
```

提供：

```python
create_app()
```

负责：

- 创建 Flask App；
- Flask 配置；
- Blueprint 注册；
- Authentication 集成；
- Flask teardown。

`create_app()` 不负责：

- 创建 Runtime Controller Thread；
- 自动启动 sing-box；
- 执行无限循环；
- 下载二进制。

这些由：

```text
run.py
+
runtime
```

负责。

这样能够避免：

- pytest 创建 App 时启动后台任务；
- Flask ReLoader 启动两套 Runtime；
- import 模块时产生运行副作用。

---

# 40. 前端架构

第一版 Web 前端保持轻量：

```text
Flask Template
+
HTML
+
CSS
+
Vanilla JavaScript
+
fetch
```

不需要：

- React；
- Vue；
- Node.js Build Chain；
- SPA Framework。

Desktop 和 Mobile 使用响应式布局。

具体页面结构由：

```text
docs/06-web-ui.md
```

定义。

---

# 41. 项目目录结构

第一版目录结构如下：

```text
proxyhub/
├── app/
│   ├── __init__.py
│   ├── settings.py
│   ├── auth.py
│   ├── logger.py
│   ├── utils.py
│   ├── routes.py
│   ├── checker.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── subscription.py
│   │   ├── node.py
│   │   ├── inbound.py
│   │   ├── outbound.py
│   │   ├── route.py
│   │   └── system.py
│   │
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── state.py
│   │   ├── controller.py
│   │   └── auto.py
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── subscription.py
│   │   ├── node.py
│   │   ├── inbound.py
│   │   ├── outbound.py
│   │   ├── route.py
│   │   └── references.py
│   │
│   ├── singbox/
│   │   ├── __init__.py
│   │   ├── protocol.py
│   │   ├── config.py
│   │   ├── process.py
│   │   ├── clash.py
│   │   └── upgrade.py
│   │
│   └── parser/
│       ├── __init__.py
│       ├── base.py
│       ├── ss.py
│       ├── vmess.py
│       ├── vless.py
│       ├── trojan.py
│       └── hysteria2.py
│
├── templates/
│   └── index.html
│
├── tests/
│
├── data/
│   ├── bin/
│   │   └── sing-box
│   ├── proxyhub.db
│   ├── settings.json
│   ├── session.secret
│   ├── config.json
│   └── config.previous.json
│
├── logs/
│
├── docs/
│   ├── 00-project-plan.md
│   ├── 01-requirements.md
│   ├── 02-architecture.md
│   ├── 03-data-model.md
│   ├── 04-singbox-design.md
│   ├── 05-runtime-control.md
│   ├── 06-web-ui.md
│   ├── 07-api.md
│   ├── 08-test-plan.md
│   └── 09-deployment.md
│
├── Dockerfile
├── docker-compose.yml
├── docker-compose.override.example.yml
├── requirements.txt
├── setup.sh
├── run.py
├── .gitignore
└── .dockerignore
```

目录结构只冻结模块级边界。

模块内部具体函数和小文件可以随着详细设计调整。

---

# 42. 测试友好性要求

核心模块必须能够脱离 Flask HTTP 层单独测试。

例如：

- Parser；
- Subscription Diff；
- Cascade Preview；
- SQLite Transaction；
- Protocol Mapping；
- Config Builder；
- Checker；
- AUTO Control；
- Settings Validation。

业务代码应避免直接依赖：

```text
flask.request
flask.g
```

这些对象只能存在于 Web Adapter 层。

同时禁止模块 import 时：

- 启动线程；
- 打开数据库；
- 创建日志文件；
- 启动 sing-box；
- 发起网络请求。

所有有副作用的行为必须由明确函数调用触发。

---

# 43. 错误处理原则

第一版错误主要分为：

```text
Validation Error
Business Conflict
External Operation Error
Internal Error
```

Web 层负责将其转换为用户可理解的 HTTP Response。

详细错误写入日志。

不得将敏感信息直接放入：

- HTTP Error；
- Exception；
- Log。

---

# 44. 第一版明确不引入的组件

第一版架构明确不使用：

```text
SQLAlchemy
Alembic

PostgreSQL
MySQL

Redis
Celery
RQ
APScheduler

RabbitMQ
Kafka

Microservices
RPC
Event Bus

Distributed Lock

Multiple Flask Workers

通用 Dependency Injection Framework

复杂 Repository Framework

React
Vue
Node.js Build Chain
```

后续只有出现明确需求时才重新评估。

---

# 45. 后续设计文档边界

本文完成后，后续设计按以下顺序展开。

## 03-data-model.md

负责：

- SQLite Schema；
- 表结构；
- 字段；
- Primary Key；
- Foreign Key；
- Index；
- Node Pool；
- priority；
- Current / Fallback；
- Cascade Transaction；
- Preview 数据一致性。

---

## 04-singbox-design.md

负责：

- Node 协议字段；
- ProxyHub → sing-box Mapping；
- Inbound；
- Selector；
- DIRECT；
- Route；
- Clash API；
- Config Builder；
- sing-box check；
- Binary Download / Upgrade。

---

## 05-runtime-control.md

负责：

- Runtime State 数据结构；
- management state；
- process state；
- Start / Stop / Restart；
- Runtime Control Lock；
- Controller Loop；
- Node Health；
- AUTO Control；
- Watchdog；
- Restart Recovery。

---

## 06-web-ui.md

负责：

- 页面；
-导航；
-桌面布局；
-移动布局；
-Preview / Confirm UX；
-running / stopped 页面状态。

---

## 07-api.md

负责：

- API Path；
- Method；
- Request；
- Response；
- Error；
- Authentication。

---

# 46. 架构冻结条件

本架构设计满足以下条件后可以冻结：

- 技术栈确定；
- Flask + SQLite / sqlite3 确定；
- 单进程模型确定；
- 单 Runtime Controller 确定；
- 单 sing-box 子进程确定；
- Runtime Control Lock 边界确定；
- SQLite / Settings / Runtime State 的数据归属确定；
- Web / Service / DB / Runtime / sing-box 模块职责确定；
- 模块依赖方向确定；
- 项目目录结构确定；
- 后续专题设计边界确定。

冻结后，以下变化通常不需要修改架构文档：

- 函数名；
- 小型 helper；
- 类名；
- 单个模块内部文件拆分；
- SQL 具体实现；
- API 路径；
- HTML 布局。

以下变化属于架构变更：

- 单进程改为多进程；
- SQLite 改为其他数据库；
- sqlite3 改为 ORM 体系；
- 引入 Redis / Celery；
- 引入独立 Scheduler；
- 多 Runtime Worker；
- 微服务拆分；
- 状态从内存迁移到外部持久化系统。

---

# 47. 架构结论

ProxyHub 第一版采用：

```text
Python
+
Flask
+
SQLite / sqlite3
+
requests
+
threading
+
ThreadPoolExecutor
+
subprocess
```

构成单机单体应用。

运行结构：

```text
1 ProxyHub Python Process
        │
        ├── Flask Web / API
        │
        └── 1 Runtime Controller Thread
                    │
                    └── 1 sing-box Process
```

数据状态分为：

```text
业务配置
→ SQLite

应用 Settings
→ settings.json

Runtime State
→ Memory

sing-box Config
→ Generated File
```

关键运行操作统一通过：

```text
runtime_control_lock
```

串行执行。

系统保持明确的模块职责：

```text
Web
→ HTTP

Service
→ 业务编排

DB
→ 持久化

Parser
→ 协议解析

Checker
→ Node 检测

sing-box
→ 外部代理引擎集成

Runtime
→ 生命周期、进程守护和 AUTO 控制
```

该架构作为后续：

```text
03-data-model.md
04-singbox-design.md
05-runtime-control.md
```

的统一设计基础。
