对于 ProxyHub 这种**个人开发、需求已经基本收敛、后续主要由你 + AI/Codex 实施**的项目，我更建议叫 **《项目实施计划》**，而不是做一份偏企业流程的“项目管理计划”。

重点应该是：**每一阶段做什么、产出什么文档、什么条件下才能进入下一阶段、Codex 在哪个阶段介入**。你原来的需求清单本身也明确要求需求确认后再分别进行数据模型、状态机、页面流程、技术架构和验收设计，这个顺序是合理的。

下面这份可以直接作为项目中的 `docs/00-project-plan.md`。

# ProxyHub 个人版项目实施计划

> 文档版本：v0.1
> 项目阶段：需求收敛 / 开发准备
> 适用版本：ProxyHub 新版本第一版
> 文档用途：指导项目从需求冻结、设计、开发、测试到发布的完整实施过程。

---

## 1. 项目目标

ProxyHub 是一个供个人使用、自行部署的本地代理网关管理工具。

项目以 sing-box 作为唯一代理运行引擎，通过 Web 管理界面完成订阅、节点、入站、出站和 Route 的管理，并提供节点健康检测、自动故障切换、手动节点切换、sing-box 生命周期管理等功能。

第一版目标不是建设通用代理管理平台，而是在保持架构简单、行为明确和长期稳定运行的前提下，完成个人实际使用所需的核心功能。

---

## 2. 实施原则

### 2.1 先需求，后设计，最后编码

项目按照以下顺序推进：

```text
需求讨论
    ↓
需求冻结
    ↓
需求规范
    ↓
数据模型设计
    ↓
运行时状态机设计
    ↓
sing-box 配置与控制设计
    ↓
Web 页面与内部 API 设计
    ↓
开发
    ↓
测试与验收
    ↓
发布
```

不得在核心需求尚未冻结时大规模进入代码实现。

---

### 2.2 需求与实现设计分离

需求文档只描述：

> 系统应该做什么。

设计文档描述：

> 系统如何实现。

例如以下内容属于需求：

* 当前节点连续失败达到阈值后切换应急节点；
* 下一控制周期扫描出站池；
* 从可用普通候选节点中选择人工优先级最高的节点。

以下内容属于设计：

* Python 类如何划分；
* 数据库使用哪些表；
* 控制循环具体函数结构；
* 锁如何实现；
* HTTP Client 使用什么库。

两类内容原则上不混写。

---

### 2.3 优先保证行为确定性

对于自动故障切换、订阅刷新、级联删除、sing-box 启停等关键行为，应尽可能做到：

* 输入明确；
* 状态明确；
* 执行顺序明确；
* 异常结果明确；
* 不依赖隐含规则；
* 不让开发者自行猜测产品行为。

---

### 2.4 第一版控制复杂度

第一版坚持：

* 单用户；
* 单 ProxyHub 实例；
* 单 sing-box 进程；
* 单后台控制循环；
* 检测批次内部有限并发；
* 不引入分布式任务系统；
* 不引入多进程共享状态；
* 不实现配置热重载；
* 不实现历史健康统计；
* 不进行超出实际使用场景的架构抽象。

只有明确需求证明现有模型无法满足时，才增加新的系统复杂度。

---

## 3. 项目文档体系

项目正式文档统一存放于：

```text
docs/
```

建议最终结构：

```text
docs/
├── 00-project-plan.md
├── 01-requirements.md
├── 02-data-model.md
├── 03-runtime-state-machine.md
├── 04-singbox-design.md
├── 05-web-ui.md
├── 06-api.md
├── 07-acceptance-tests.md
├── 08-deployment.md
└── history/
    └── requirements-discussion.md
```

各文档职责如下。

| 文档                                   | 主要内容                                  |
| ------------------------------------ | ------------------------------------- |
| `00-project-plan.md`                 | 项目实施阶段、顺序、交付物和完成条件                    |
| `01-requirements.md`                 | ProxyHub 第一版正式需求                      |
| `02-data-model.md`                   | 数据实体、字段、关系、持久化边界                      |
| `03-runtime-state-machine.md`        | 控制循环、健康检测、故障切换和状态转换                   |
| `04-singbox-design.md`               | ProxyHub 到 sing-box 配置及 Clash API 的映射 |
| `05-web-ui.md`                       | 页面结构、操作流程及桌面/移动端行为                    |
| `06-api.md`                          | Web 前后端内部 API                         |
| `07-acceptance-tests.md`             | 功能及场景验收标准                             |
| `08-deployment.md`                   | Docker Compose 和 Ubuntu venv 部署方案     |
| `history/requirements-discussion.md` | 原始需求讨论和历史决策记录                         |

正式设计和开发以 `01-requirements.md` 为需求基准。

历史讨论文档只用于追溯决策，不作为开发行为的直接依据。

---

# 4. 第一阶段：需求冻结

## 4.1 目标

将当前《ProxyHub 个人版需求讨论清单》整理为正式、连续、无讨论痕迹的需求规范。

---

## 4.2 主要工作

### 4.2.1 完成需求一致性检查

重点检查：

* 是否仍存在前后冲突；
* 同一行为是否在不同章节出现不同描述；
* 是否存在已经废弃但未删除的旧需求；
* 协议列表是否统一；
* 自动出站“生效”的定义是否统一；
* 健康检测与连续失败计数来源是否统一；
* 自动切换执行周期是否统一；
* 全局扫描第一版是否确认为预留功能；
* 删除和订阅刷新级联规则是否完整。

---

### 4.2.2 整理正式需求规范

把讨论编号重新整理为按功能领域组织的需求，例如：

```text
REQ-NODE-xxx
REQ-SUB-xxx
REQ-INBOUND-xxx
REQ-OUTBOUND-xxx
REQ-ROUTE-xxx
REQ-HEALTH-xxx
REQ-FAILOVER-xxx
REQ-RUNTIME-xxx
REQ-UI-xxx
REQ-SETTINGS-xxx
REQ-DEPLOY-xxx
```

每条正式需求原则上只表达一个可验证行为。

---

### 4.2.3 补充完整业务场景

至少形成以下场景：

1. 首次安装与配置；
2. 正常运行；
3. 自动出站当前节点故障；
4. 应急节点及普通节点全部不可用；
5. 手动刷新订阅失败；
6. 订阅刷新删除节点并触发出站和 Route 级联删除；
7. 人工停止、修改配置并重新启动；
8. sing-box 意外退出并自动恢复。

---

## 4.3 阶段交付物

```text
docs/01-requirements.md
docs/history/requirements-discussion.md
```

---

## 4.4 完成条件

只有同时满足以下条件，才能进入设计阶段：

* [ ] 正式需求规范已经完成；
* [ ] 所有核心业务行为没有已知冲突；
* [ ] 没有未决的 P0/P1 需求问题；
* [ ] 第一版明确不做的功能已经列明；
* [ ] 自动故障切换完整场景能够从头到尾解释；
* [ ] 订阅刷新和删除级联完整场景能够解释；
* [ ] 所有关键状态均有明确行为。

完成后，将需求规范标记为：

```text
Requirements v1.0
```

---

# 5. 第二阶段：数据模型设计

## 5.1 目标

根据已经冻结的业务需求设计最小、清晰且可维护的数据模型。

---

## 5.2 核心实体

第一版主要围绕：

```text
Subscription
Node
Inbound
Outbound
Route
Settings
```

设计。

需要重点确定：

* Subscription 与 Node 的关系；
* Node 来源；
* 自建节点与订阅节点的区别；
* Outbound 与 Node 的多对多关系；
* 自动出站普通候选节点顺序；
* 自动出站应急节点；
* Manual Outbound 保存的当前节点；
* Route 与 Inbound 的一对零或一关系；
* Route 与 Outbound 的多对一关系；
* 删除时的数据库和业务级级联行为。

---

## 5.3 明确持久化边界

必须明确区分：

### 数据库状态

例如：

* Subscription；
* Node；
* Inbound；
* Outbound；
* Route；
* Manual 当前选择；
* 用户设置。

### 内存运行状态

例如：

* 最近一次健康结果；
* Delay；
* 是否正在检测；
* 连续失败次数；
* 自动出站当前运行节点；
* 全节点不可用开始时间；
* 检测调度时间；
* sing-box 运行时状态。

不得因为实现方便，把已经确定为运行时状态的数据随意加入数据库。

---

## 5.4 阶段交付物

```text
docs/02-data-model.md
```

建议同时包含：

* ER 图；
* 表说明；
* 字段说明；
* 唯一约束；
* 外键；
* 删除规则；
* 示例数据。

---

## 5.5 完成条件

* [ ] 每一个需求实体均能映射到数据模型；
* [ ] 不存在没有业务用途的表；
* [ ] 自动/手动/direct Outbound 均可表达；
* [ ] Emergency 和 Candidate 关系明确；
* [ ] Manual 当前节点能够持久化；
* [ ] 自动运行节点没有被错误持久化；
* [ ] 订阅刷新可以稳定识别新增、修改、删除；
* [ ] 所有级联删除规则能够实现。

---

# 6. 第三阶段：运行时状态机设计

## 6.1 目标

在编码前完整确定 ProxyHub 最核心的运行行为。

这一阶段属于整个项目最重要的技术设计阶段之一。

---

## 6.2 控制循环设计

需要明确一个控制周期中任务的执行顺序。

基本模型：

```text
开始周期
    ↓
检查 sing-box 进程
    ↓
处理正在生效的自动出站
    ↓
执行当前节点检测
    ↓
处理达到连续失败阈值的出站
    ↓
处理已经位于应急节点的出站
    ↓
执行其他到期任务
    ↓
周期结束
    ↓
sleep 15 秒
    ↓
下一周期
```

15 秒为两个任务周期之间的固定等待时间，不要求形成严格的墙钟 15 秒调度。

---

## 6.3 自动出站状态机

至少需要明确：

```text
普通节点运行
    ↓
当前节点检测失败
    ↓
连续失败计数
    ↓
达到失败阈值
    ↓
立即切 Emergency
    ↓
本周期结束
    ↓
sleep
    ↓
下一周期扫描整个出站池
    ↓
存在普通可用节点？
    ├── 是 → 选择人工优先级最高节点 → 切换 → 正常状态
    └── 否 → 保持 Emergency
```

并进一步定义：

* 多个自动出站同时故障；
* Emergency 本身不可用；
* 全池不可用；
* 全池恢复；
* sing-box 重启；
* 用户人工停止；
* Settings 改变；
* 出站被多个 Route 复用。

---

## 6.4 健康检测模型

明确区分：

```text
last_health:
- unknown
- available
- unavailable

checking:
- true
- false
```

“检测中”不覆盖最近一次已经确定的健康结果。

同时明确：

只有：

> 控制循环发起的当前节点检测

参与自动出站连续失败计数。

以下检测只更新健康显示结果，不增加或清零连续失败次数：

* 故障池扫描；
* 页面人工检测；
* 后续预留的全局扫描。

---

## 6.5 阶段交付物

```text
docs/03-runtime-state-machine.md
```

文档应至少包含：

* 控制循环流程图；
* Auto Outbound 状态图；
* 健康状态定义；
* 连续失败计数规则；
* 全节点不可用计时；
* sing-box 生命周期；
* 关键异常路径。

---

## 6.6 完成条件

* [ ] 任意时刻能够说明一个 Auto Outbound 当前处于什么状态；
* [ ] 任意检测结果能够明确说明会修改哪些状态；
* [ ] 自动切换不存在两个合理但不同的执行顺序；
* [ ] 多个 Auto Outbound 同时故障的行为明确；
* [ ] ProxyHub/sing-box 重启后的状态明确；
* [ ] 人工停止与自动恢复不会发生逻辑冲突。

---

# 7. 第四阶段：sing-box 集成设计

## 7.1 目标

明确数据库中的 ProxyHub 业务对象如何转换为 sing-box 配置及运行时操作。

---

## 7.2 重点设计内容

### 节点映射

支持：

* VMess；
* VLESS；
* Trojan；
* Shadowsocks；
* Hysteria2。

明确每种协议支持的字段及分享 URI 映射。

---

### Inbound 映射

支持：

* HTTP；
* SOCKS；
* Mixed；
* Shadowsocks；
* VMess。

---

### Outbound 映射

明确：

```text
Node → sing-box 独立 outbound
Manual Outbound → selector
Auto Outbound → selector
Direct Outbound → direct
```

全局 Node 全部写入 sing-box 配置。

ProxyHub 创建的 Manual/Auto Selector 也写入配置。

只有被 Route 实际引用的 Auto Outbound 运行自动状态机。

---

### Clash API

明确：

* Delay API；
* Selector 当前节点读取；
* Selector 切换；
* HTTP 状态码判断；
* `delay > 0`；
* API 监听地址；
* Existing connection 中断策略。

---

## 7.3 配置生命周期

需要设计：

```text
数据库
    ↓
生成临时配置
    ↓
sing-box check
    ↓
成功？
├── 否 → 保持 stopped
└── 是
      ↓
正式配置
      ↓
启动 sing-box
```

并保留上一次可用配置用于人工排错。

---

## 7.4 阶段交付物

```text
docs/04-singbox-design.md
```

---

## 7.5 完成条件

* [ ] 所有 Node 协议均有明确配置映射；
* [ ] Inbound 映射完整；
* [ ] Manual/Auto/Direct 映射完整；
* [ ] Route 能生成正确 sing-box 配置；
* [ ] Clash API 能完成检测和切换；
* [ ] 配置检查失败路径完整；
* [ ] 配置生命周期无隐含状态。

---

# 8. 第五阶段：Web UI 与内部 API 设计

## 8.1 目标

在正式开发页面之前确定信息架构和用户操作流程。

---

## 8.2 Desktop 页面

建议至少包括：

```text
Dashboard
Subscriptions
Nodes
Inbounds
Outbounds
Routes
Settings
Logs / Status
sing-box Management
```

---

## 8.3 Mobile 页面

移动端第一版只提供：

* 整体状态；
* Auto Outbound 状态；
* 节点健康状态；
* Manual Outbound 当前节点；
* Manual Outbound 节点切换。

不提供完整配置管理。

---

## 8.4 页面状态规则

明确：

### sing-box running

禁止：

* 刷新订阅；
* 新增/修改/删除节点；
* 修改 Inbound；
* 修改 Outbound 结构；
* 修改 Route。

允许：

* 查看状态；
* 人工节点检测；
* Manual Outbound 切换；
* Auto Outbound 普通候选优先级修改；
* Settings 中不改变 sing-box 配置的设置修改；
* 停止/restart sing-box。

### sing-box stopped

开放完整结构配置。

---

## 8.5 内部 API

API 只服务 ProxyHub Web 前端。

不以稳定公共 API 为设计目标。

首先从页面操作反推 API，不提前构建通用 REST 平台。

---

## 8.6 阶段交付物

```text
docs/05-web-ui.md
docs/06-api.md
```

---

# 9. 第六阶段：验收标准设计

## 9.1 目标

在编码前明确“做到什么程度算完成”。

---

## 9.2 Requirement Traceability

每个正式需求原则上应能够对应：

```text
REQ-xxx
    ↓
实现模块
    ↓
测试用例
```

例如：

```text
REQ-FAILOVER-003
→ runtime/failover
→ AT-FAILOVER-003
```

---

## 9.3 测试分类

至少包括：

### 单元测试

适用于：

* Parser；
* Subscription Diff；
* Filter/Exclude；
* 优先级；
* 数据校验；
* 配置转换。

### 集成测试

适用于：

* 数据库；
* 配置生成；
* sing-box check；
* Clash API；
* Selector 切换；
* 节点检测。

### 场景测试

适用于：

* 自动故障切换；
* 全池不可用；
* sing-box 意外退出；
* 订阅刷新；
* 级联删除；
* 启停修改配置流程。

---

## 9.4 阶段交付物

```text
docs/07-acceptance-tests.md
```

---

# 10. 第七阶段：开发实施

## 10.1 开发顺序

不建议按页面一个页面地从前往后开发。

建议按照依赖关系开发。

### 第一批：基础数据层

```text
Settings
Subscription
Node
Inbound
Outbound
Route
```

完成：

* Schema；
* CRUD；
* 基础校验；
* 关系约束。

---

### 第二批：节点与订阅

完成：

* Clash 订阅请求；
* Subscription Parser；
* Filter / Exclude；
* Diff；
* 自建节点；
* URI 解析；
* 删除级联。

---

### 第三批：sing-box Config Builder

完成：

* Node outbound；
* Inbound；
* Selector；
* Direct；
* Route；
* Clash API 配置；
* 配置检查。

这一阶段首先做到：

> 数据库能够稳定生成正确 sing-box 配置。

---

### 第四批：sing-box 生命周期

完成：

* 下载；
* 版本；
* start；
* stop；
* restart；
* process watchdog；
* expected state。

---

### 第五批：节点健康检测

完成：

* TCP 快检；
* Hysteria2 特殊处理；
* URL Delay；
* 有限并发；
* 内存 Health State；
* 人工检测。

---

### 第六批：Auto Outbound 状态机

完成：

* 当前节点检测；
* 连续失败；
* Emergency；
* 下一周期 Pool Scan；
* Candidate 选择；
* 全池不可用；
* sing-box 重启恢复。

---

### 第七批：Web Desktop

完成完整管理界面。

---

### 第八批：Mobile

完成简化移动页面。

---

### 第九批：日志和完善

完成：

* 后端日志；
* 关键事件；
* 日志下载；
* 错误提示；
* UX 收尾。

---

# 11. AI / Codex 使用原则

Codex 主要用于执行已经明确的设计，不负责自行重新定义核心需求。

每次开发任务尽量限定范围。

例如：

```text
根据：
- docs/01-requirements.md
- docs/02-data-model.md

实现 Node 和 Subscription 数据层。

本次不要实现：
- sing-box
- health check
- failover
- Web UI
```

避免一次要求：

> 实现整个 ProxyHub。

---

## 11.1 单次开发任务建议结构

每个任务至少包含：

### 目标

本次实现什么。

### 依据

需要阅读哪些设计文档。

### 范围

允许修改哪些模块。

### 不做

明确禁止顺手实现哪些后续功能。

### 验收

本次任务完成的判断条件。

---

## 11.2 AI 不得自行改变需求

发现以下情况时，应停止扩展实现并提出问题：

* 需求之间存在冲突；
* 设计无法满足需求；
* sing-box 实际能力与设计假设不一致；
* 必须增加新的业务概念才能继续；
* 实现需要突破第一版明确不做的范围。

---

# 12. 代码提交与阶段控制

建议以相对小的功能提交推进开发。

示例：

```text
feat: add subscription model
feat: add node parser
feat: add subscription diff
feat: add outbound data model
feat: add singbox config builder
feat: add clash delay client
feat: add runtime health state
feat: add automatic failover
```

尽量避免：

```text
feat: implement proxyhub
```

这种包含大量不同功能的大提交。

---

# 13. 阶段评审

每个大阶段完成后执行一次小型 Review。

Review 重点不是代码风格，而是：

1. 是否满足需求；
2. 是否引入需求之外的新行为；
3. 是否增加了不必要复杂度；
4. 是否破坏后续设计；
5. 是否存在无法测试的隐式状态。

存在重大问题时，先修正当前阶段，不急于进入下一阶段。

---

# 14. 第一版发布前验收

第一版发布前至少完整执行以下真实场景。

## 14.1 首次安装

```text
全新环境
→ 启动 ProxyHub
→ 下载 sing-box
→ 创建完整配置
→ 成功运行代理
```

---

## 14.2 正常运行

```text
Auto Outbound 使用普通节点
→ 当前节点周期检测成功
→ 长期保持运行
```

---

## 14.3 当前节点故障

```text
连续检测失败达到阈值
→ 当前周期切 Emergency
→ sleep
→ 下一周期 Pool Scan
→ 找到普通节点
→ 自动恢复普通节点
```

---

## 14.4 全池不可用

```text
普通节点故障
→ Emergency
→ Pool Scan 全失败
→ 保持 Emergency
→ 达到等待时间
→ sing-box 重启
→ Runtime 状态重新初始化
```

---

## 14.5 Manual Outbound

验证：

* 多节点；
* 人工切换；
* 重启保持；
* 不参与自动 Failover。

---

## 14.6 Subscription Refresh

分别测试：

* 正常新增；
* 修改；
* 删除；
* Filter；
* Exclude；
* 结果为空；
* 请求失败；
* 格式错误；
* 重复 Name；
* 删除 Emergency；
* 删除普通 Candidate；
* 级联删除 Outbound；
* 级联删除 Route。

---

## 14.7 Process Recovery

测试：

```text
人工 kill sing-box
→ ProxyHub 控制循环发现
→ 自动启动
→ Runtime 状态重新初始化
```

---

# 15. 第一版完成标准

只有同时满足以下条件，ProxyHub v1 才视为完成：

* [ ] Requirements v1.0 全部实现；
* [ ] 数据模型稳定；
* [ ] sing-box 配置可以稳定生成和检查；
* [ ] Manual Outbound 工作正常；
* [ ] Auto Outbound 自动故障切换完整；
* [ ] sing-box 生命周期管理完整；
* [ ] Subscription Refresh 安全可靠；
* [ ] Desktop 管理功能完整；
* [ ] Mobile 基本状态和手动切换可用；
* [ ] 关键日志完整；
* [ ] Docker Compose 部署通过；
* [ ] Ubuntu venv 部署通过；
* [ ] 核心验收场景全部通过；
* [ ] 第一版明确不做的功能没有被无意引入。

---

# 16. 后续版本管理

第一版发布后，新增需求不直接修改代码。

建议流程：

```text
提出新需求
    ↓
加入需求讨论
    ↓
确认需求
    ↓
更新 Requirements
    ↓
判断是否影响 Data Model / State Machine / API
    ↓
修改设计
    ↓
开发
```

对于第二版及以后功能，可以建立：

```text
docs/roadmap.md
```

但第一版开发期间，不建议提前建设复杂 Roadmap 系统。

---

# 17. 当前项目下一步

当前阶段的执行顺序确定为：

1. 完成现有需求讨论清单最后一致性检查；
2. 将讨论清单整理成正式 `01-requirements.md`；
3. 补充完整业务和异常场景；
4. 冻结 `Requirements v1.0`；
5. 编写 `02-data-model.md`；
6. 编写 `03-runtime-state-machine.md`；
7. 编写 `04-singbox-design.md`；
8. 编写 Web UI、API 和验收标准；
9. 正式进入代码开发。

在 `Requirements v1.0` 冻结前，不开始大规模代码重构或正式功能开发。
