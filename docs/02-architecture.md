# ProxyHub V1.0 软件架构设计

> 文档版本：v1.0
> 文档状态：已确认
> 更新日期：2026-09-18
> 需求基线：[ProxyHub V1.0 需求规范](01-requirements.md)

本文确定 ProxyHub V1.0 的技术选型、项目组织方式，以及各部分如何协作。数据表与约束、sing-box 字段映射、运行控制规则、页面和 API 契约分别在后续专题设计中展开。

主要对应需求：REQ-GEN-007、REQ-MODEL-004、REQ-CONFIG-001～012、REQ-RUNTIME-001～007、REQ-SETTINGS-001～006、REQ-REL-001～002。

## 1. 技术选型

| 用途 | 选型 | 在系统中的作用 |
|---|---|---|
| 开发语言 | Python 3 | 实现 Web、业务逻辑和运行控制 |
| Web 与页面 | Flask、Jinja2、HTML/CSS、原生 JavaScript | 提供管理页面和页面使用的内部 API |
| 业务数据 | SQLite、Python `sqlite3` | 保存 Subscription、Node、Inbound、Outbound、Route 等业务对象 |
| 应用设置 | JSON | 保存 Settings；由独立模块加载、校验和原子写入 |
| HTTP 请求 | `requests` | 获取订阅、访问 sing-box 控制接口和检查远程版本 |
| TCP 检测 | Python `socket` | 检测 Node 的 TCP 连通性 |
| 后台控制与状态同步 | `threading.Thread`、`threading.Lock` | 运行唯一控制循环，串行化运行控制并保护共享状态 |
| 批量健康检测 | `concurrent.futures.ThreadPoolExecutor` | 按单次检测任务创建线程池，限制批量 Node 检测并发数 |
| sing-box 进程 | `subprocess` | 检查配置、启动、停止和查询进程 |
| 日志与测试 | Python `logging`、pytest | 记录运行事件并验证核心模块 |

业务数据直接使用 `sqlite3` 访问。页面由 Flask 模板渲染，通过 `fetch` 调用内部 API；CSS 和 JavaScript 作为 `static/` 文件直接加载。桌面和移动页面可复用基础模板与样式，具体页面组织由 Web UI 设计确定。部署目标为 Docker Compose 和 Ubuntu Python/venv，两种方式使用相同的业务数据与 Settings 格式。

## 2. 总体架构

### 2.1 系统组成

ProxyHub 是一个 Python 单体应用，以 sing-box 作为唯一代理引擎。浏览器通过 Flask 管理业务配置和运行状态；ProxyHub 将数据库中的业务对象生成 sing-box 配置，并通过子进程及控制接口管理 sing-box。

```text
浏览器
  │ HTTP
  ▼
Flask 页面 / 内部 API
  │
  ▼
业务 Service ──────── Parser（订阅和分享 URI）
  │
  ├── DB（SQLite）
  └── Runtime（运行控制与内存状态）
         ├── Checker（Node 健康检测）
         └── singbox 集成层
                ├── 配置生成与检查
                ├── 子进程管理
                └── 控制接口 ──────────► sing-box 进程
```

`Service` 编排用户操作，`Runtime` 管理正在运行的系统，`singbox` 集成层封装与代理引擎的交互。Web 层只处理认证、请求与响应，并把业务操作交给 Service。

### 2.2 进程与线程

一个部署实例运行一个 ProxyHub Python 进程，最多管理一个 sing-box 子进程。ProxyHub 进程内有 Flask 请求线程和一个后台控制线程；单次批量健康检测按 Settings 中的并发上限使用临时 `ThreadPoolExecutor`。同一数据目录只由这一个 ProxyHub 实例使用。

```text
ProxyHub Python 进程
├── Flask 请求线程
├── 1 个 Runtime Controller 线程
└── 健康检测工作线程（按检测任务创建）

sing-box 子进程（最多 1 个）
```

后台控制线程按周期执行进程守护和 Routed AUTO 控制。一个周期结束后再等待 Control Interval，然后开始下一周期。Start、Stop、Restart 和后台恢复共用 Runtime 的进程生命周期入口。

## 3. 项目结构

### 3.1 目录结构

目录按职责划分；下图确定模块级结构，模块内部文件可随专题设计细化。

```text
proxyhub/
├── app/
│   ├── __init__.py       # Flask App Factory
│   ├── web/
│   │   ├── pages.py      # 页面路由
│   │   ├── auth.py       # 管理员认证与会话
│   │   └── api/          # 按业务域划分的内部 API
│   ├── services/         # 用户操作与业务事务
│   ├── db/               # SQLite 连接和数据访问
│   ├── parser/           # 订阅与分享 URI 解析
│   ├── runtime/          # 运行状态、控制循环和 AUTO
│   ├── singbox/          # 配置、进程、控制接口和二进制管理
│   ├── checker.py        # Node 健康检测
│   ├── settings.py       # Settings 加载、校验和保存
│   └── logger.py         # 日志初始化
├── templates/            # Flask 页面模板
├── static/               # 页面样式和脚本
├── tests/                # 自动化验证
├── data/                 # 数据库、Settings、密钥、生成配置和二进制
├── logs/                 # 运行日志
├── docs/                 # 需求与设计文档
├── run.py                # 应用启动入口
└── requirements.txt     # Python 依赖
```

Docker Compose、Dockerfile 和 Ubuntu 安装脚本位于项目根目录；具体文件与部署步骤由部署设计确定。

### 3.2 模块职责

| 模块 | 主要职责 |
|---|---|
| `web/`、模板与静态资源 | 页面路由、认证，以及按业务域组织的内部 API；负责输入与响应转换 |
| `services/` | 校验并编排 Subscription、Node、Inbound、Outbound、Route 和系统操作；确定业务事务范围 |
| `db/` | 管理 SQLite 连接、事务基础能力和实体数据访问 |
| `parser/` | 将订阅内容或单条分享 URI 转成标准 Node 数据 |
| `runtime/` | 保存运行状态，统一执行 sing-box 生命周期控制、后台循环和 AUTO 决策 |
| `checker.py` | 执行 TCP 与 URL 检测，返回健康检测结果 |
| `singbox/` | 生成和检查配置，管理子进程、控制接口及二进制文件 |
| `settings.py`、`logger.py` | 管理应用设置与日志初始化 |

### 3.3 依赖方向

页面和内部 API 调用 Service；Service 调用 DB、Parser、Runtime、Checker 或 sing-box 集成层完成业务操作。Runtime 使用 DB 读取当前业务配置，调用 Checker 和 sing-box 集成层执行运行控制。DB、Parser 和 sing-box 集成层向上返回数据或执行结果，业务规则由 Service 或 Runtime 的对应职责处理。

```text
Web / API → Service → DB、Parser、Runtime、Checker、singbox
                          Runtime → DB、Checker、singbox
```

Flask App Factory 负责创建应用、配置项目根目录下的 `templates/` 与 `static/`、注册 Web 路由和认证；`run.py` 负责启动顺序，并在启动时确定数据与日志目录的绝对路径，作为只读启动配置交给 Settings、DB 和 Runtime。导入模块和创建 Flask App 本身不触发后台循环、数据库写入、网络请求或 sing-box 启动，使核心模块能够独立验证。

## 4. 数据与状态归属

| 数据类别 | 权威来源 | 主要内容与使用方式 |
|---|---|---|
| 业务数据 | `data/proxyhub.db` | Subscription、Node、Inbound、MANUAL/AUTO、Route、Node Pool、priority、Default Node；配置生成和业务校验读取最新数据 |
| 应用设置 | `data/settings.json` | 检测、控制、Web 监听和认证等参数；启动时加载，管理修改后完成校验与原子保存 |
| 管理与进程状态 | ProxyHub 进程内存及子进程观测 | `running` / `stopped` 管理状态、sing-box 进程句柄与实际运行情况 |
| Runtime State | ProxyHub 进程内存 | Node 健康结果、Routed MANUAL/AUTO 的 Current Node、AUTO 计数与计时 |
| 认证密钥 | `data/session.secret` | Flask 会话签名所需密钥，独立于普通 Settings |
| sing-box 配置 | `data/config.json` 等生成文件 | 根据业务数据生成的运行产物；保留最近一次成功运行的配置用于排错 |

DIRECT 是系统内置 Outbound，不占用业务数据记录。MANUAL/AUTO 的 Default Node 保存在 SQLite；被 Route 引用的 MANUAL/AUTO 才具有当前运行周期的 Current Node。每次成功 Start 或 Restart 后，Runtime 从 Default Node 初始化这些 Current Node，并重置 Node 健康结果及 AUTO 计数和计时。Node Pool priority 只作为业务数据供 AUTO 决策读取，不进入 sing-box 配置。

Settings 保存采用完整校验、临时文件写入和原子替换。运行任务使用任务开始时取得的有效 Settings；直接修改配置文件后的内容在 ProxyHub 下次启动时加载。sing-box 配置由最新数据库数据生成，业务对象不从生成文件反向恢复。

## 5. 运行与并发设计

### 5.1 后台控制循环

唯一的 Runtime Controller 顺序处理每个控制周期：管理状态为 `running` 时，先检查 sing-box 进程；进程存在时依次处理 Routed AUTO，进程缺失时尝试恢复并结束本周期。管理状态为 `stopped` 时，控制线程等待下一周期。

Checker 同时服务于 AUTO 检测和用户发起的人工检测。单个 Node 依次完成 TCP、URL 检测，URL 检测照常执行，不取决于 TCP 结果；批量 Node 使用受限线程池并发检测。AUTO 与人工检测分别控制各自批次的并发数。每个 Node 检测完成时一次性写入健康结果，并发结果按完成先后覆盖；AUTO 决策直接使用本次检测结果。

### 5.2 运行控制锁

Runtime 持有一把进程内运行控制锁。后台完整控制周期、Start、Stop、Restart、结构配置写入、priority 调整、MANUAL 在线切换，以及 sing-box 下载或升级替换，通过这把锁串行执行。Restart 的 Stop 和 Start 在同一次持锁期间连续完成。

结构配置写入在取得锁后检查管理状态为 `stopped`，然后进入数据库事务。priority 调整在 `running` 和 `stopped` 状态均可执行。Subscription Refresh、Settings 保存和人工健康检测可以与上述操作并发。Settings 保存请求开始时检查管理状态为 `stopped`，保存过程不取得运行控制锁。

### 5.3 数据库连接与事务

每个需要访问 SQLite 的操作在线程内取得连接，操作结束后关闭；Web 请求通过 Flask teardown 清理连接。Service 确定跨表业务事务的边界，并将同一连接传给相关 DB 模块；DB 模块执行数据访问。Subscription Sync 确认、级联删除等涉及多个对象的修改在一个事务内提交或回滚。Preview 读取现状并形成影响结果；Confirm 在持锁后重新检查所需数据，再执行事务。

## 6. 关键协作流程

### 6.1 应用启动与 sing-box 启动

```text
run.py
  → 初始化日志和运行目录
  → 加载、补全并校验 Settings
  → 初始化 SQLite 与 Runtime
  → 创建 Flask App
  → sing-box 二进制存在且数据库中有 Route 时：读取最新业务数据 → 生成临时配置
      → sing-box check → 替换正式配置 → 启动 sing-box
      → 进入 running 并初始化当前运行周期的 Runtime State
  → 启动唯一后台控制线程与 Web 服务
```

Settings 加载或校验失败时终止 ProxyHub 启动。Settings 有效，但 sing-box 二进制、Route、配置检查或进程启动条件不满足时，Web 仍启动，管理状态保持 `stopped`。配置检查失败时保留原正式配置和最近一次成功运行配置，并向页面与日志提供错误信息。

### 6.2 结构配置修改

```text
HTTP 请求 → Web/API → Service
  → 取得运行控制锁并检查操作条件
  → 开始 SQLite 事务 → 业务校验与 DB 写入 → 提交
  → 返回结果
```

Subscription、Node、Inbound、Outbound 和 Route 的结构修改在 `stopped` 状态只更新数据库，下一次 Start 再生成 sing-box 配置。Subscription Sync 和涉及级联的删除由 Service 完成 Preview/Confirm 编排；解析由 Parser 执行，多对象更新由同一事务提交。

### 6.3 运行中的协作

用户请求 Start、Stop、Restart 或 MANUAL 切换时，Service 调用 Runtime，由 Runtime 协调状态、sing-box 子进程或控制接口。MANUAL 在线切换成功后，sing-box 当前选择、运行时 Current Node 和数据库 Default Node 保持一致；未被 Route 引用的 MANUAL 仅更新 Default Node。后台 AUTO 则由 Runtime Controller 调用 Checker 获取检测结果，再通过 sing-box 集成层执行节点切换并更新 Runtime State。

这些流程只确定模块间的责任和顺序；数据约束、sing-box 字段、状态转换、页面交互与 API 格式在对应专题设计中细化。
