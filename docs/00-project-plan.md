# ProxyHub 个人版项目实施计划

> 文档版本：v1.0
> 适用范围：ProxyHub 新版本第一版
> 文档用途：规定需求冻结后，从设计、开发、测试到第一版发布的实施顺序、阶段产出和完成条件。
> 当前阶段：Requirements v1.0 已冻结，进入核心设计。

---

## 1. 项目目标

ProxyHub 是供个人使用、自行部署的本地代理网关管理工具。

项目以 sing-box 作为唯一代理运行引擎，通过 Web 管理：

- Subscription；
- Node；
- Inbound；
- MANUAL / AUTO / DIRECT Outbound；
- Route；
- Node 健康检测；
- MANUAL Current Node；
- AUTO 自动故障恢复；
- sing-box 生命周期；
- Settings、日志和升级。

第一版以：

> 功能完整、行为确定、结构简单、容易排错

为主要目标。

不以建设通用代理平台、多用户系统、复杂任务系统或企业级高可用系统为目标。

正式业务需求统一以：

```text
docs/01-requirements.md
```

为准。

---

# 2. 实施原则

## 2.1 Requirements 是唯一业务基准

`01-requirements.md` 描述：

> 系统应该做什么。

后续设计文档只描述：

> 系统如何实现这些需求。

设计和开发不得重新定义已有业务行为。

如果设计过程中发现需求无法实现、存在冲突或必须增加新的业务概念，应先回到需求层确认，而不是在代码中自行补充规则。

---

## 2.2 不重复设计已经明确的业务规则

新版 Requirements 已经明确大量运行规则，包括：

- Subscription / Node / Inbound / Outbound / Route 的关系；
- MANUAL / AUTO / DIRECT 的行为；
- priority；
- Current Node；
- Fallback Node；
- Route 引用规则；
- 结构配置修改限制；
- Subscription 同步和级联删除；
- sing-box Start / Stop / Restart；
- 运行控制锁；
- Node 健康检测；
- AUTO 故障恢复；
- Settings；
- Web 功能范围；
- sing-box 下载和升级。

后续设计文档不得重新发明第二套业务规则。

设计阶段重点回答：

```text
这些需求具体由哪些模块实现？
数据保存在哪里？
模块之间如何调用？
异常如何返回？
如何映射为 sing-box 配置？
如何测试？
```

---

## 2.3 按依赖推进，不采用完整瀑布流程

项目不要求所有设计文档全部完成后才开始编码。

推荐采用：

```text
Requirements 冻结
        ↓
核心设计
        ↓
核心后端开发
        ↓
Web / API 设计
        ↓
Web / API 开发
        ↓
集成与验收
        ↓
部署与发布
```

其中：

```text
数据模型
sing-box 集成
运行控制
```

属于核心设计，原则上应在对应核心代码大规模开发前确定。

Web UI、内部 API 和部署细节可以在核心后端结构稳定后继续完善。

---

## 2.4 设计保持最小化

第一版只设计当前需求真正需要的能力。

原则上不提前建立：

- 通用任务系统；
- Event Bus；
- Plugin 系统；
- Repository 抽象体系；
- 分布式锁；
- 多 worker；
- 多进程状态同步；
- 配置版本状态机；
- Pending Config；
- 通用 Workflow；
- 通用消息通知框架；
- 为未来版本准备的大量抽象层。

如果普通函数、类、事务和一把进程内锁已经能够满足需求，就不增加额外架构。

---

## 2.5 测试跟随开发

不采用：

```text
全部功能开发完成
→ 最后统一补测试
```

而采用：

```text
实现一个模块
→ 完成对应单元/集成测试
→ Review
→ 再进入下一模块
```

最终再执行完整场景验收。

---

# 3. 项目文档体系

正式文档统一放置于：

```text
docs/
```

建议结构：

```text
docs/
├── 00-project-plan.md
├── 01-requirements.md
├── 02-data-model.md
├── 03-singbox-design.md
├── 04-runtime-control.md
├── 05-web-ui.md
├── 06-api.md
├── 07-test-plan.md
├── 08-deployment.md
└── history/
    └── requirements-discussion.md
```

各文档职责如下：

| 文档 | 职责 |
|---|---|
| `00-project-plan.md` | 项目阶段、实施顺序、交付物和完成条件 |
| `01-requirements.md` | 第一版正式业务需求 |
| `02-data-model.md` | 数据库实体、字段、关系、约束、事务和持久化边界 |
| `03-singbox-design.md` | Node / Inbound / Outbound / Route 到 sing-box 的映射，以及 Clash API、配置生成和升级 |
| `04-runtime-control.md` | 应用运行状态、内存状态、控制循环、运行控制锁、健康检测和 AUTO 控制实现 |
| `05-web-ui.md` | Desktop / Mobile 页面、信息结构和用户操作流程 |
| `06-api.md` | Web 前端使用的内部 API |
| `07-test-plan.md` | 单元测试、集成测试和场景验收 |
| `08-deployment.md` | Docker Compose 和 Ubuntu venv 部署 |
| `history/` | 历史讨论和决策记录，不作为开发直接依据 |

---

# 4. 第一阶段：Requirements 冻结

## 4.1 目标

形成 ProxyHub 第一版稳定业务基线。

阶段状态：已完成。

阶段产出：

```text
docs/01-requirements.md
```

版本：

```text
Requirements v1.0
```

---

## 4.2 完成条件

进入正式设计前应确认：

- Requirements 已完成；
- 核心业务关系不存在已知冲突；
- MANUAL / AUTO / DIRECT 行为明确；
- Route 行为明确；
- stopped / running 下允许和禁止的操作明确；
- Subscription 同步和级联删除明确；
- sing-box 生命周期明确；
- Node 健康检测明确；
- AUTO 故障恢复流程明确；
- 第一版明确不做的能力已经确定；
- 不存在阻塞设计的 P0/P1 未决问题。

Requirements 冻结后，普通实现问题不再修改需求。

只有业务行为本身发生改变时才进行需求变更。

---

# 5. 第二阶段：数据模型设计

产出：

```text
docs/02-data-model.md
```

## 5.1 目标

把 Requirements 中需要持久化的数据转换为最小数据库模型。

核心对象：

```text
Subscription
Node
Inbound
Outbound
Outbound Node Pool
Route
```

同时明确：

```text
Settings → settings.json
运行状态 → 内存
DIRECT → 系统内置对象
```

---

## 5.2 重点设计

需要确定：

### Subscription / Node

- Subscription 表；
- Subscription 与 Node 的关系；
- 自建 Node 与订阅 Node 的来源表达；
- Node 的稳定身份；
- Subscription 同步匹配需要的字段；
- Subscription 元信息。

### Outbound

数据库只保存用户创建的：

```text
MANUAL
AUTO
```

明确：

- Node Pool；
- priority；
- MANUAL Current Node；
- AUTO Fallback Node；
- type 转换；
- Node Pool 最少两个 Node；
- Node 在多个 Outbound 中复用。

DIRECT 不建立普通数据库记录。

### Route

明确：

```text
Route
→ 一个 Inbound
→ 一个 Outbound
```

并保证：

- 一个 Inbound 最多属于一个 Route；
- 一个 Outbound 可以被多个 Route 引用；
- DIRECT 使用稳定系统标识表示。

---

## 5.3 事务和级联设计

重点设计统一业务事务：

```text
删除 Node
删除 Subscription
同步 Subscription 删除 Node
```

需要能够：

```text
计算影响
→ 返回预览
→ 用户确认
→ 一个事务完成：
   Subscription
   Node
   Outbound
   Route
```

并实现 Requirements 中规定的：

- priority 重排；
- Current Node 自动替换；
- Fallback Node 自动替换；
- Node Pool 少于两个时删除 Outbound；
- 继续级联删除 Route。

---

## 5.4 完成条件

- 每个持久化需求都能够映射到明确字段；
- 没有无业务用途的数据表；
- MANUAL / AUTO 可以完整表达；
- DIRECT 不被错误建模成普通 Outbound；
- priority 有稳定数据结构；
- MANUAL Current Node 可以持久化；
- AUTO Current Node 没有被持久化；
- AUTO Fallback Node 可以持久化；
- Subscription 同步能够稳定识别节点；
- 所有删除和级联规则能够在一个事务中实现。

完成后可以开始数据库和 Domain 层开发。

---

# 6. 第三阶段：sing-box 集成设计

产出：

```text
docs/03-singbox-design.md
```

## 6.1 目标

定义：

> ProxyHub 业务对象如何转换成 sing-box 配置，以及 ProxyHub 如何控制 sing-box。

---

## 6.2 Node 映射

为以下协议建立字段矩阵：

```text
VMess
VLESS
Trojan
Shadowsocks
Hysteria2
```

明确：

- ProxyHub 字段；
- 分享 URI 字段；
- sing-box 字段；
- 必填字段；
- 可选字段；
- Reality；
- uTLS；
- WebSocket；
- gRPC；
- HTTP/2；
- Shadowsocks obfs。

已有代码只能作为参考。

最终以新版设计确认的字段矩阵为准。

---

## 6.3 Inbound 映射

定义各类 Inbound 到 sing-box 的转换。

同时处理：

- tag；
- listen；
- port；
- 用户输入校验；
- 明显端口冲突。

---

## 6.4 Outbound 和 Route 映射

明确：

```text
Node
→ sing-box proxy outbound

MANUAL
→ selector

AUTO
→ selector

DIRECT
→ direct outbound

Route
→ Inbound 到 Outbound 的 routing
```

配置 Builder 必须按照 Routed 对象生成运行配置。

未被 Route 引用的 Inbound、MANUAL、AUTO 不生成对应运行对象。

---

## 6.5 Selector

明确：

### MANUAL

生成配置时：

```text
数据库 Current Node
→ selector 默认节点
```

### AUTO

生成配置时：

```text
Fallback Node
→ selector 默认节点
```

并支持：

```text
interrupt_exist_connections
```

满足节点切换后已有连接中断的需求。

---

## 6.6 Clash API

设计最小 Client，支持：

- Node URL Delay；
- selector Current Node 查询；
- selector 节点切换；
- Clash API 可用性判断；
- HTTP / JSON 错误处理。

不建立通用 Clash API SDK。

---

## 6.7 配置生命周期

实现模型：

```text
最新数据库
    ↓
生成临时配置
    ↓
sing-box check
    ↓
检查成功
    ↓
原子替换正式配置
    ↓
启动 sing-box
```

同时：

- 保留上一份可用正式配置供人工排错；
- check 失败不自动恢复旧运行配置；
- stopped 下普通结构修改只改数据库，不生成配置。

---

## 6.8 sing-box 二进制管理

明确：

- 二进制路径；
- 当前版本检测；
- GitHub Release 获取；
- amd64 资产选择；
- 下载；
- 临时文件；
- 校验；
- 原子替换；
- 升级失败保护。

版本筛选等具体策略在本文中规定，不额外增加需求。

---

## 6.9 完成条件

- 五种 Node 协议映射明确；
- Inbound 映射完整；
- MANUAL / AUTO / DIRECT 映射完整；
- Routed 配置裁剪明确；
- Route 可以生成正确配置；
- selector 默认节点规则明确；
- Clash API 行为明确；
- 配置 check / 替换 / 启动流程明确；
- 下载和升级方案明确。

完成后可以实现 Config Builder 和 sing-box Client。

---

# 7. 第四阶段：运行控制设计

产出：

```text
docs/04-runtime-control.md
```

第一版不设计额外复杂状态机。

---

## 7.1 目标

实现 Requirements 已经确定的：

```text
管理状态
实际进程状态
运行控制锁
后台控制循环
Node Health State
AUTO Runtime State
```

---

## 7.2 状态边界

明确三类数据。

### 持久化业务数据

数据库：

```text
Subscription
Node
Inbound
MANUAL / AUTO
Route
MANUAL Current Node
AUTO Fallback Node
```

### Settings

```text
data/settings.json
```

### Runtime State

只存在于内存，例如：

```text
Node Health
TCP Delay
URL Delay
Last Checked
Failure Reason

AUTO Current Node
Failure Count
Fallback Started Time
Priority Recovery Timer

sing-box Process State
```

---

## 7.3 管理状态和进程状态

实现：

```text
management_state:
running
stopped
```

同时独立观察：

```text
process running
process exited
start failed
not installed
```

禁止用进程是否存在替代管理状态。

---

## 7.4 运行控制锁

系统只使用一把进程内运行控制锁。

需要明确哪些操作持锁：

```text
Start
Stop
Restart
后台控制周期
结构配置写操作
MANUAL 在线切换
sing-box 下载 / 升级替换
后台恢复 Restart
```

以及哪些操作不持锁：

```text
Settings 保存
人工 Node 检测
```

实现时不得另外建立任务队列或复杂锁体系。

---

## 7.5 后台控制循环

实现固定流程：

```text
控制周期
    ↓
进程守护
    ↓
AUTO 控制
    ↓
等待基础间隔
    ↓
下一周期
```

如果本周期触发 sing-box Restart：

```text
立即结束当前周期
```

---

## 7.6 Node 健康检测

统一 Node 检测实现：

```text
TCP Test
    ↓
URL Delay
    ↓
更新 Health State
```

明确：

- available / unavailable / unknown；
- TCP Delay；
- URL Delay；
- Failure Reason；
- Last Checked；
- Max Concurrency；
- Hysteria2 与其他 Node 使用相同检测流程；
- 人工检测；
- AUTO 检测。

不同检测来源不得错误修改 AUTO failure count。

---

## 7.7 AUTO 控制

不额外建立状态枚举。

每个 Routed AUTO 只维护 Requirements 规定的少量运行数据。

控制流程实现为普通条件流程：

```text
Current == Fallback
→ Fallback Recovery
→ Fallback Timeout

Current == Candidate
→ Current Check
→ Failover
→ Priority Recovery
```

重点实现：

- Fallback Recovery；
- Current Candidate 连续失败；
- Candidate → Fallback；
- Priority Recovery；
- Fallback 超时 Restart；
- selector 切换失败；
- Restart 后全部 Runtime State 初始化。

---

## 7.8 完成条件

- 任意运行数据属于 DB / Settings / Memory 中哪一类都明确；
- Start / Stop / Restart 顺序明确；
- 锁范围明确；
- 后台控制周期没有隐藏并发；
- Node Health 数据修改规则明确；
- AUTO 控制可以直接翻译为代码；
- sing-box 意外退出恢复明确；
- Restart 后 Runtime 初始化明确；
- 不存在额外隐式状态机。

完成后可以实现完整 Runtime 层。

---

# 8. 第五阶段：核心后端开发

完成前三份核心设计后，可以正式进入核心后端实现。

不需要等待 Web UI、API 和 Deployment 文档全部完成。

推荐按以下批次实施。

---

## 8.1 第一批：应用基础和 Settings

实现：

- 项目目录结构；
- 配置路径；
- data 目录；
- Settings 默认值；
- Settings 加载；
- 缺失字段补全；
- 完整校验；
- 原子保存；
- Logging 基础设施；
- 单实例基础保护。

完成对应测试。

---

## 8.2 第二批：数据库与基础业务模型

实现：

```text
Subscription
Node
Inbound
Outbound
Outbound Node Pool
Route
```

以及：

- CRUD；
- 唯一约束；
- 外键；
- priority；
- Current / Fallback；
- type 转换；
- 基础业务校验。

完成数据库单元和集成测试。

---

## 8.3 第三批：Subscription 和 Node

实现：

- Subscription 请求；
- Subscription Parser；
- Filter；
- Exclude；
- Diff；
- Subscription 信息刷新；
- 自建 Node；
- URI Parser；
- Node 修改和删除。

然后实现：

```text
影响计算
→ Preview
→ Confirm
→ Transaction
```

以及完整级联规则。

---

## 8.4 第四批：sing-box Config Builder

实现：

- Node outbound；
- Inbound；
- MANUAL selector；
- AUTO selector；
- DIRECT；
- Route；
- Clash API 配置；
- Routed 对象裁剪；
- 临时配置；
- sing-box check；
- 正式配置原子替换。

阶段目标：

> 数据库能够稳定生成符合 Requirements 的 sing-box 配置。

---

## 8.5 第五批：sing-box 生命周期

实现：

- binary version；
- download；
- upgrade；
- Start；
- Stop；
- Restart；
- management state；
- process state；
- process watchdog；
- runtime 初始化；
- 运行控制锁。

阶段目标：

> ProxyHub 可以稳定控制一个 sing-box 进程。

---

## 8.6 第六批：Node Health

实现：

- TCP Test；
- URL Delay；
- Hysteria2 检测；
- Health State；
- 检测并发；
- 单 Node 人工检测；
- 批量人工检测。

完成独立测试后再进入 AUTO。

---

## 8.7 第七批：AUTO 控制

实现：

- Routed AUTO 初始化；
- Fallback Recovery；
- Current Candidate 检测；
- failure count；
- Candidate → Fallback；
- Priority Recovery；
- Fallback Timeout；
- Restart Recovery；
- selector 切换失败处理。

完成后应能够在没有 Web UI 的情况下通过测试完整验证 AUTO 行为。

---

# 9. 第六阶段：Web UI 与内部 API 设计

核心后端结构基本稳定后，完成：

```text
docs/05-web-ui.md
docs/06-api.md
```

---

## 9.1 UI 设计原则

页面直接围绕 Requirements 中已有对象和操作设计。

不增加新的业务层。

桌面页面至少包括：

```text
Status / Dashboard
Subscriptions
Nodes
Inbounds
Outbounds
Routes
Settings
Logs
sing-box Management
```

移动页面只实现 Requirements 明确允许的状态查看和 MANUAL 在线切换。

---

## 9.2 stopped / running 页面状态

页面必须根据管理状态明确表现：

```text
enabled
disabled
read-only
hidden
```

而不是仅依赖后端报错。

重点覆盖：

### stopped

允许完整结构配置。

### running

禁止结构修改。

但仍允许 Requirements 明确规定的在线行为，例如：

- 查看状态；
- Subscription 信息刷新；
- Node 人工检测；
- MANUAL 在线 Current Node 切换；
- 在线 Settings；
- Stop；
- Restart。

---

## 9.3 内部 API

API 只服务 ProxyHub 自己的 Web 前端。

不以公共 API 为目标。

设计原则：

```text
页面操作
    ↓
业务 Service
    ↓
内部 API
```

而不是：

```text
先建设通用 REST 平台
→ 再寻找页面用途
```

API 应清晰表达：

- CRUD；
- Preview / Confirm；
- Start / Stop / Restart；
- MANUAL switch；
- Node detect；
- Subscription info refresh；
- Subscription sync；
- Settings；
- status；
- logs；
- upgrade。

---

# 10. 第七阶段：Web 开发

## 10.1 后端 API

先实现：

- API route；
- request validation；
- error response；
- auth；
- session；
- status API；
- 业务 Service 调用。

不得在 API Controller 内重新实现 Domain 规则。

---

## 10.2 Desktop

完成完整配置管理页面。

重点保证：

- stopped / running 状态；
- 级联删除 Preview；
- Subscription sync Preview；
- Node priority；
- MANUAL Current；
- AUTO Fallback；
- DIRECT；
- Node Health；
- lifecycle；
- upgrade；
- 关键错误反馈。

---

## 10.3 Mobile

只实现：

- 管理状态；
- 实际进程状态；
- MANUAL / AUTO 状态；
- Node Health；
- DIRECT 状态；
- MANUAL Current Node 在线切换。

不复制 Desktop 完整配置页面。

---

# 11. 第八阶段：测试与验收

产出：

```text
docs/07-test-plan.md
```

测试从开发开始同步建立，本阶段主要进行完整集成和场景验收。

验收设计不属于 Requirements 冻结内容。本阶段基于 Requirements v1.0 建立需求到测试用例的对应关系，并明确各业务场景的前置条件、操作步骤和预期结果。

---

## 11.1 单元测试

重点：

- Parser；
- URI Parser；
- Filter / Exclude；
- Subscription Diff；
- priority；
- 业务校验；
- 级联影响计算；
- Config Builder；
- Settings 校验；
- AUTO 条件判断。

---

## 11.2 集成测试

重点：

- SQLite；
- 业务事务；
- sing-box check；
- sing-box lifecycle；
- Clash API；
- selector switch；
- Node detect；
- Settings 保存；
- auth；
- API。

---

## 11.3 必测场景

### 首次安装

```text
没有 sing-box
→ Web 正常运行
→ 下载 sing-box
→ 创建配置
→ Start
→ 正常代理
```

### 无 Route 启动

```text
数据库没有 Route
→ Start 失败
```

### DIRECT

```text
Inbound
→ DIRECT Route
→ Start
→ 正常直连
```

### 结构配置冻结

```text
running
→ 尝试修改 Subscription / Node / Inbound / Outbound / Route
→ 禁止
```

### running 在线操作

验证：

- Subscription 信息刷新；
- Node 人工检测；
- MANUAL 在线切换；
- 允许在线生效的 Settings；
- Stop；
- Restart。

### Subscription Sync

覆盖：

- 新增 Node；
- 修改 Node；
- 删除 Node；
- Filter；
- Exclude；
- 空结果；
- 请求失败；
- parser 失败；
- 影响预览；
- Current 自动替换；
- Fallback 自动替换；
- Outbound 级联删除；
- Route 级联删除；
- 事务失败。

### MANUAL

验证：

- 默认 Current；
- 结构编辑 Current；
- running 在线切换；
- 持久化；
- Clash API 查询实际 Current；
- 切换失败不修改数据库；
- Restart 后恢复数据库 Current。

### AUTO 初始化

```text
Start / Restart
→ Current = Fallback
→ 下一周期 Fallback Recovery
```

### AUTO Candidate 故障

```text
Current Candidate
→ 连续 URL 检测失败
→ 达到阈值
→ 切换 Fallback
→ 下一周期扫描 Candidate
→ 恢复可用 Candidate
```

### Priority Recovery

```text
当前 Candidate 不是最高 priority
→ Priority Recovery 到期
→ 检测更高 priority Candidate
→ 可用则切换
```

### Fallback 超时

```text
长期无法恢复 Candidate
→ Fallback Timeout
→ Restart
→ Runtime State 重新初始化
```

### sing-box 意外退出

```text
management_state = running
→ kill sing-box
→ watchdog 检测
→ 从最新数据库重新生成配置
→ check
→ start
→ Runtime State 重置
```

### selector 切换失败

分别验证：

- Candidate → Fallback；
- Fallback → Candidate；
- Priority Recovery。

### Settings

验证：

- 文件不存在；
- 缺少字段；
- 非法 JSON；
- 非法字段；
- 页面原子保存；
- 在线设置即时用于后续任务；
- 直接修改 JSON 只在 ProxyHub 重启后生效。

### Authentication

验证：

- 空密码无需登录；
- 非空密码要求登录；
- 内部 API 受保护；
- 日志下载受保护；
- 修改账号后旧 Session 失效。

### sing-box Upgrade

验证：

- 未安装；
- stopped；
- running；
- 下载失败；
- 校验失败；
- 升级成功；
- 升级后保持 stopped。

---

# 12. 第九阶段：部署和发布

产出：

```text
docs/08-deployment.md
```

---

## 12.1 Docker Compose

验证：

- data 持久化；
- 日志；
- 端口；
- sing-box 二进制；
- 容器重启；
- 升级；
- 正常 Start / Stop。

---

## 12.2 Ubuntu Python / venv

验证：

```text
Ubuntu 20.04+
amd64
Python / venv
```

包括：

- 依赖安装；
- 目录；
- 权限；
- 启动；
- 停止；
- 日志；
- 升级。

---

# 13. 开发批次总览

推荐最终开发顺序：

```text
1. Settings / App 基础
        ↓
2. Database / Domain Model
        ↓
3. Subscription / Node
        ↓
4. Outbound / Route / Cascade
        ↓
5. sing-box Config Builder
        ↓
6. sing-box Lifecycle + Runtime Lock
        ↓
7. Node Health
        ↓
8. AUTO Control
        ↓
9. Internal API + Auth
        ↓
10. Desktop Web
        ↓
11. Mobile Web
        ↓
12. Upgrade / Logs / UX 收尾
        ↓
13. Integration / Acceptance
        ↓
14. Deployment / Release
```

每一批都应满足：

```text
实现
→ 测试
→ Review
→ 合并
```

再进入下一批。

---

# 14. AI / Codex 使用原则

Codex 主要负责：

> 根据已经确认的 Requirements 和设计实现代码。

不负责自行设计新的业务规则。

---

## 14.1 单次任务尽量小

推荐：

```text
目标：
实现 Subscription Diff 和同步预览。

依据：
- docs/01-requirements.md
- docs/02-data-model.md

范围：
- subscription service
- diff
- tests

本次不做：
- Web UI
- sing-box
- AUTO

验收：
相关 Requirements 和测试全部通过。
```

避免：

```text
实现 ProxyHub 后端
```

这种范围过大的任务。

---

## 14.2 AI 必须遵循文档优先级

优先级：

```text
01-requirements.md
        ↓
对应设计文档
        ↓
现有代码
```

如果旧代码与正式 Requirements 冲突：

> 修改旧代码。

不得因为“原来就是这样实现”而修改需求。

---

## 14.3 发现设计问题时停止扩展

出现以下情况时，不应由 AI 自行发挥：

- Requirements 相互冲突；
- sing-box 实际能力不满足需求假设；
- 设计无法满足 Requirements；
- 必须增加新的业务对象；
- 必须突破第一版明确边界；
- 存在两种明显不同且都会改变用户行为的实现。

应先进行设计或需求确认。

---

# 15. Commit 和 Review

提交应围绕单一功能。

例如：

```text
feat: add settings loader
feat: add outbound schema
feat: add subscription diff
feat: add cascade preview
feat: add singbox config builder
feat: add runtime control lock
feat: add node health checker
feat: add auto fallback recovery
feat: add priority recovery
```

避免：

```text
feat: implement proxyhub
```

---

每个开发批次完成后进行 Review，重点检查：

1. 是否满足 Requirements；
2. 是否违反设计；
3. 是否引入需求之外的行为；
4. 是否增加不必要复杂度；
5. 是否存在隐藏持久化状态；
6. 是否存在未经设计的并发；
7. 是否有测试覆盖关键行为。

---

# 16. 第一版完成标准

ProxyHub v1 只有同时满足以下条件才视为完成：

- Requirements v1.0 已全部实现；
- 数据模型稳定；
- Subscription / Node 完整可用；
- 删除和同步级联事务正确；
- Inbound / Outbound / Route 完整可用；
- DIRECT 工作正常；
- MANUAL Current Node 工作正常；
- AUTO 故障恢复完整；
- Node Health 工作正常；
- sing-box 配置生成和 check 稳定；
- sing-box 生命周期管理稳定；
- process watchdog 正常；
- 运行控制锁行为正确；
- Settings 行为符合 Requirements；
- Authentication 正常；
- Desktop 功能完整；
- Mobile 第一版功能完整；
- 日志和下载正常；
- sing-box 下载和升级正常；
- Docker Compose 部署通过；
- Ubuntu venv 部署通过；
- 核心验收场景全部通过；
- 第一版明确不做的功能没有被无意引入。

---

# 17. 后续需求变更

Requirements v1.0 冻结后，新需求不直接进入代码。

流程：

```text
提出需求
    ↓
判断是否属于 Bug / Design / Requirement
    ↓
如果改变用户可见业务行为
    ↓
修改 Requirements
    ↓
评估影响：
Data Model
sing-box Design
Runtime
UI
API
Tests
    ↓
更新设计
    ↓
开发
```

如果只是：

- 内部类结构；
- 数据库实现细节；
- 协议字段映射细节；
- 错误码；
- API 路径；
- 页面布局；
- sing-box Release 筛选方式；

且不改变正式业务行为，则直接修改对应设计文档，不需要修改 Requirements。

---

# 18. 当前项目下一步

当前执行顺序建议为：

```text
1. 编写 docs/02-data-model.md

2. 编写 docs/03-singbox-design.md

3. 编写 docs/04-runtime-control.md

4. Review 三份核心设计

5. 开始核心后端开发：
   Settings
   → Database
   → Subscription / Node
   → Outbound / Route
   → Config Builder
   → Lifecycle
   → Health
   → AUTO

6. 核心后端接口稳定后：
   编写 docs/05-web-ui.md
   编写 docs/06-api.md

7. 开发 Desktop / Mobile Web

8. 完善 docs/07-test-plan.md
   明确验收标准并执行完整集成与场景验收

9. 完成 docs/08-deployment.md

10. Docker / Ubuntu 实机验收

11. 发布 ProxyHub v1
```

目前最直接的下一项工作是：

> **编写并评审 `docs/02-data-model.md`。**
