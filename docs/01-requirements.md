# ProxyHub 个人版第一版需求规范

> 文档版本：v0.1（初稿）
>
> 文档状态：待评审
>
> 更新日期：2026-08-26
>
> 适用范围：ProxyHub 新版本第一版

## 0. 文档说明

本文描述 ProxyHub 第一版“应该做什么”，是后续数据模型、状态机、sing-box 集成、页面、API 和验收设计的需求基准。

本文尚未冻结。评审完成并解决遗留问题后，版本升级为 `Requirements v1.0`。历史讨论只用于追溯，不作为开发依据：

- `docs/history/requirements-discussion-v1.txt`
- `docs/history/requirements-discussion-v2.txt`
- `docs/history/requirements-open-questions-v0.1.md`

需求编号按功能领域组织。每条需求只表达一组紧密相关、可以验证的产品行为。

---

## 1. 产品目标与实施边界

### 1.1 产品目标

**REQ-GEN-001** ProxyHub 是供单人使用、自行部署的本地代理网关管理工具。

**REQ-GEN-002** 系统接收机场订阅节点和用户自建节点，将远程节点组织为本地代理入站，供本机或其他设备使用。

**REQ-GEN-003** 系统以 sing-box 作为唯一代理引擎，提供节点健康检测、自动故障恢复、手动节点切换及 sing-box 生命周期管理。

### 1.2 第一版原则

**REQ-GEN-004** 第一版服务个人家庭实际使用，不以公共服务、多用户平台、企业部署或通用代理管理平台为目标。

**REQ-GEN-005** 第一版优先保证主要行为简单、确定、可排错，不为低概率异常建立复杂恢复状态、分布式任务、历史任务或企业级高可靠机制。

**REQ-GEN-006** 系统只支持单 ProxyHub 实例、单 Web 进程、单 sing-box 进程和单后台控制循环。同一数据目录不得同时运行多个 ProxyHub 实例。

---

## 2. 业务模型与基本约束

### 2.1 核心关系

Subscription 管理由该订阅产生的 Node。自建 Node 不属于任何 Subscription。

Node 是全局对象，可以被不同的 Outbound 复用。

Route 表示一个 Inbound 到一个 Outbound 的映射。具体引用约束见 2.3 节。

Outbound 分为以下三种类型：

- Manual Outbound：包含一个或多个 Node；
- Auto Outbound：包含一个 Fallback Node，以及一个或多个按人工优先级排序的 Candidate Node；
- Direct Outbound：不包含 Node，流量直接访问目标地址。

### 2.2 名词

- **Subscription**：用户保存的机场订阅及其 Filter/Exclude 设置。
- **Node**：一个可生成 sing-box 远程出站的代理节点，来源为订阅或自建。
- **Inbound**：向本机或其他设备提供服务的本地监听入口。
- **Outbound**：Route 的流量出口，分为 Manual Outbound、Auto Outbound 和 Direct Outbound。
- **Route**：一个 Inbound 到一个 Outbound 的映射。
- **Manual Outbound**：由用户人工选择 Current Node，不执行自动故障切换的 Outbound。
- **Auto Outbound**：由后台控制循环管理 Current Node，并在节点故障时自动恢复代理能力的 Outbound。
- **Direct Outbound**：不包含 Node，流量直接访问目标地址的 Outbound。
- **Node Pool**：Manual Outbound 或 Auto Outbound 包含的 Node 集合。
- **Candidate Node**：Auto Outbound 中参与人工优先级排序的普通候选 Node。
- **Fallback Node**：Auto Outbound 故障时优先切换的独立备用 Node，不参与 Candidate Node 排序。
- **Current Node**：Manual Outbound 或 Auto Outbound 当前在 sing-box selector 中选择的 Node。
- **Routed Auto Outbound**：至少被一条 Route 引用的 Auto Outbound。该名称只表示 Route 引用关系，不表示 sing-box 当前一定处于 running 状态。

### 2.3 全局不变量

**REQ-MODEL-001** 每条 Route 必须同时引用一个 Inbound 和一个 Outbound。一个 Inbound 最多绑定一条 Route；一个 Outbound 可以被零条、一条或多条 Route 引用。

**REQ-MODEL-002** 多条 Route 引用同一个 Outbound 时，共享该 Outbound 的 Node Pool、Current Node 和运行状态。

**REQ-MODEL-003** Node 是全局实体。同一个 Node 可以加入多个 Manual Outbound 或 Auto Outbound，但在同一个 Node Pool 中只能出现一次。

**REQ-MODEL-004** 数据库只持久化 Subscription、Node、Inbound、Outbound、Route，以及用户为 Manual Outbound 选择的 Current Node。应用 Settings 持久化在独立的 `data/settings.json` 文件中。健康结果、延迟、检测状态、失败计数和 Auto Outbound 运行状态只保存在内存中。

---

## 3. 核心使用场景

### 3.1 首次安装与配置

```text
启动 ProxyHub Web
→ sing-box 未安装或没有有效 route，保持 stopped
→ 用户下载 sing-box
→ 添加订阅或自建节点
→ 创建 Outbound、Inbound 和 Route
→ 用户点击 Start
→ 生成并检查配置
→ 检查成功后启动 sing-box
```

### 3.2 正常运行

```text
sing-box 实际启动或重启成功
→ 已生效 Auto Outbound 初始选择 Fallback Node
→ 清空 Auto Outbound 临时运行状态并开始记录 Fallback 持续时间
→ 下一控制周期扫描全部 Candidate Node
→ 选择可用 Candidate 中人工优先级最高者
→ 后续每个控制周期检测 Current Candidate
→ Current Candidate 不是最高优先级时，按独立间隔扫描更高优先级 Candidate
```

### 3.3 当前节点故障恢复

```text
当前 Candidate 连续检测失败达到阈值
→ 本周期立即切换 Fallback Node
→ 本 Auto Outbound 本周期处理结束
→ 下一个控制周期扫描全部 Candidate Node
→ 有可用 Candidate：切换到最高优先级可用节点
→ 没有可用 Candidate：保持 Fallback Node
```

### 3.4 Fallback 持续超时恢复

```text
Auto Outbound 的 Current Node 为 Fallback Node
→ 每个控制周期先扫描全部 Candidate Node
→ 有可用 Candidate：切换到最高优先级可用节点并结束 Fallback 状态
→ 没有可用 Candidate：保持 Fallback Node
→ 持续处于 Fallback 达到配置超时时间：重启整个 sing-box
→ 清空运行时状态并重新执行初始选择
```

### 3.5 订阅刷新

```text
sing-box stopped
→ 用户请求刷新
→ 请求、解析、过滤和校验
→ 跳过无效或不支持的节点
→ 至少存在一个有效节点时生成差异预览
→ 同时展示节点变化和级联删除影响
→ 用户确认：原子更新数据
→ 用户取消：不修改任何数据
```

### 3.6 人工修改配置

```text
用户停止 sing-box
→ 修改 Subscription、Node、Inbound、Outbound 或 Route
→ 用户再次点击 Start
→ 重新生成并检查完整配置
→ 成功后启动
```

### 3.7 sing-box 意外退出

```text
期望状态为 running
→ 控制循环发现 sing-box 已退出
→ 使用当前正式配置重新启动
→ 清空运行时健康及切换状态
→ Auto Outbound 从 Fallback Node 重新初始化
→ 本控制周期结束，下一周期恢复检测和切换
```

---

## 4. 节点与协议

### 4.1 支持范围

**REQ-NODE-001** 第一版远程节点只支持以下协议：

- VMess；
- VLESS；
- Trojan；
- Shadowsocks；
- Hysteria2。

第一版不支持 TUIC。既有 parser 和 sing-box 映射只能作为上述五种协议字段的参考，不能隐式扩大协议范围。

**REQ-NODE-002** Shadowsocks 节点需要支持 sing-box 自身可用的 obfs 能力，不安装或管理额外 obfs 二进制。

**REQ-NODE-003** Reality、uTLS fingerprint、WebSocket、gRPC 和 HTTP/2 等字段组合的准确范围，在 sing-box 集成设计中形成字段矩阵和验证样例，但不得超出上述五种协议。

### 4.2 自建节点

**REQ-NODE-004** 用户可以逐项填写协议参数创建自建节点，也可以粘贴一条受支持的分享 URI，由页面解析并回填表单。第一版不提供多条 URI 或文件批量导入。

**REQ-NODE-005** 自建节点允许查看、修改、删除和人工检测。

### 4.3 保存校验

**REQ-NODE-006** Node 只有在必填字段、端口范围、协议字段和 sing-box 配置映射通过校验后才能保存或导入。所有已保存的全局 Node 都必须能够生成 sing-box 出站配置片段。

**REQ-NODE-007** 节点凭据、完整订阅 URL、UUID、密码和密钥不得写入日志或不必要地显示在差异预览中。

---

## 5. 订阅管理

### 5.1 添加与请求

**REQ-SUB-001** 系统允许维护多个订阅。订阅只在用户从页面明确发起时刷新，不执行后台定时刷新。

**REQ-SUB-002** 第一版订阅 URL 只接受具有正常有效证书的 HTTPS 地址，不支持 HTTP、局域网订阅地址、自签名证书或忽略证书校验。

**REQ-SUB-003** 订阅请求使用程序内置、固定的 Clash 兼容 User-Agent 和请求头，不允许为单个订阅配置自定义请求头。

### 5.2 Filter 与 Exclude

**REQ-SUB-004** Filter/Exclude 只匹配 Node 的 `name`：

- 忽略大小写；
- 关键词使用逗号或换行分隔，并去除关键词自身首尾空白及空项；
- 多个 Filter 关键词为 OR；Filter 为空表示不过滤；
- 多个 Exclude 关键词为 OR；
- 同时命中时 Exclude 优先；
- 不支持正则表达式、自动地区分组或复杂筛选规则。

### 5.3 解析、匹配与跳过

**REQ-SUB-005** 刷新时，无效节点和不支持协议节点全部跳过。预览需要显示跳过数量、可安全显示的节点标识和原因。只要过滤后至少剩一个合法节点，就允许进入差异确认。

**REQ-SUB-006** 如果请求失败、订阅整体格式无法识别、没有任何合法节点，或经过 Filter/Exclude 后结果为空，本次刷新失败，不产生可确认结果，原数据不变。

**REQ-SUB-007** 同一订阅刷新时，只使用 parser 产出的 `name` 完整内容作为节点身份匹配键。匹配区分大小写，不自动修剪、改写或进行 Unicode 归一化：

- 完全相同视为同一 Node；
- name 相同而其他字段变化视为修改；
- name 变化视为删除旧 Node 并新增新 Node；
- 不同订阅允许存在相同 name；
- 同一订阅出现完全相同的重复 name 时，由于身份不明确，本次刷新整体失败。

### 5.4 差异确认与事务

**REQ-SUB-008** 刷新成功解析后，页面显示新增、修改、删除和跳过节点的数量及明细；用户确认前不得修改数据库。

**REQ-SUB-009** 差异预览必须同时显示因删除节点将被删除的 Outbound 和 Route。用户确认后在一个业务事务中完成更新；用户取消时任何数据都不改变。

**REQ-SUB-010** 被跳过的节点不进入新订阅结果。因此它可能使原有同名 Node 出现在删除预览中；最终是否导入及执行级联由用户查看完整预览后确认。

**REQ-SUB-011** 订阅 Node 为只读，不能人工修改协议参数；其内容只能由订阅刷新更新。自建 Node 与订阅 Node 在页面中必须显示不同来源。

**REQ-SUB-012** 明确删除订阅时，先展示其全部 Node 及级联影响，用户确认后使用与刷新删除相同的规则处理。

---

## 6. Inbound、Outbound 与 Route

### 6.1 Inbound

**REQ-INBOUND-001** 系统允许创建任意数量的 Inbound，支持：HTTP、SOCKS、Mixed、Shadowsocks 和 VMess。

**REQ-INBOUND-002** 每个 Inbound 独立定义名称、监听协议、监听地址、监听端口和该协议所需认证参数。Mixed 在同一端口兼容 HTTP 和 SOCKS。

**REQ-INBOUND-003** 未绑定 route 的 Inbound 只保存于数据库，不写入 sing-box 配置，也不对外监听。

### 6.2 Direct Outbound

**REQ-OUTBOUND-001** Direct Outbound 不包含 Node，流量直接访问目标地址。

### 6.3 Manual Outbound

**REQ-OUTBOUND-002** Manual Outbound 至少包含一个 Node，不使用优先级，不执行自动故障切换。新建普通 Outbound 时默认类型为 Manual。

**REQ-OUTBOUND-003** Manual Outbound 可以包含多个 Node。第一个加入的 Node 成为初始当前节点；用户可以在 sing-box running 时从页面人工切换。

**REQ-OUTBOUND-004** Manual Outbound 保存稳定的节点加入顺序，但第一版不提供排序功能。人工选择的当前节点持久化；若该 Node 被移出，则回退到仍存在且最早加入的 Node。

**REQ-OUTBOUND-005** 人工切换成功后才保存新的当前节点。切换失败时保留原 selector 选择和数据库选择，并在页面提示失败。

### 6.4 Auto Outbound

**REQ-OUTBOUND-006** Auto Outbound 必须包含一个 Fallback Node 和至少一个 Candidate Node。Fallback Node 与 Candidate Node 必须是不同 Node；同一 Node 不能同时承担两个角色。

**REQ-OUTBOUND-007** Candidate 由用户手工排序。保存后系统生成连续、唯一的 1 至 N 优先级；系统不根据延迟或其他健康指标自动调整顺序。

**REQ-OUTBOUND-008** Fallback Node 不参与 Candidate Node 排序。Auto Outbound 不允许用户临时手动切换或锁定 Current Node，Current Node 完全由后台控制循环管理。

**REQ-OUTBOUND-009** Manual Outbound 转为 Auto Outbound 时必须指定 Fallback Node 并完成 Candidate Node 排序；Auto Outbound 转为 Manual Outbound 时必须明确选择新的 Current Node，否则不允许保存。

**REQ-OUTBOUND-010** 未被 route 引用的 Manual/Auto Outbound selector 仍写入 sing-box 配置，但未被引用的 Auto Outbound 不运行自动检测、切换、优先级恢复或 Fallback 超时重启控制。

### 6.5 Route 与级联

**REQ-ROUTE-001** Route 只表达一个 Inbound 到一个 Outbound 的映射，不提供规则分流或额外“服务”业务层。

**REQ-ROUTE-002** 删除 Inbound 或 Outbound 时，一并删除引用它的 Route。

**REQ-ROUTE-003** 删除 Node 后：

- 从所有 Outbound 节点池中删除其引用；
- Manual Outbound 失去全部 Node 时删除该 Outbound；
- Auto Outbound 失去 Fallback Node 或失去全部 Candidate Node 时删除该 Outbound；
- 删除上述 Outbound 后继续删除引用它们的 Route。

人工删除 Node、删除 Subscription 和订阅刷新删除 Node 都使用同一规则，并在执行前展示完整影响。

---

## 7. 配置编辑与 sing-box 配置生命周期

### 7.1 运行期间允许的修改

**REQ-CONFIG-001** sing-box running 时禁止刷新订阅，以及新增、修改或删除 Node、Inbound、Outbound 结构和 Route。

**REQ-CONFIG-002** running 时允许：查看状态、人工检测 Node、切换 Manual 当前节点、修改 Auto Candidate 顺序、修改不改变 sing-box 结构的 Settings，以及停止或重启 sing-box。

**REQ-CONFIG-003** Auto Candidate 顺序在 running 时保存后不立即检测、择优或切换；新顺序在后续 Fallback Recovery 或 Candidate Priority Recovery 选择 Candidate 时生效。

### 7.2 配置生成

**REQ-CONFIG-004** 系统不提供独立“应用配置”按钮。Start 自动执行：

```text
读取数据库
→ 生成临时完整配置
→ 执行 sing-box check
→ 成功：替换正式配置并启动
→ 失败：保持 stopped，数据库不回滚
```

**REQ-CONFIG-005** 完整配置包含：

- 所有合法的全局 Node 独立出站，包括未被任何 Outbound 引用的 Node；
- 所有已保存的 Manual/Auto selector，包括未被 route 引用者；
- Direct Outbound；
- 仅被 route 引用的 Inbound；
- 现存 route 映射；
- 仅监听本机的 Clash API。

生成 Auto Outbound selector 时固定以其 Fallback Node 作为 sing-box 启动后的初始选择，不在配置生成或启动前检测 Candidate Node。

**REQ-CONFIG-006** 系统保留上一份可用正式配置供人工排错，但新配置检查失败后不自动恢复或启动旧配置。

**REQ-CONFIG-007** 对会写入配置的 Inbound 执行基本监听地址和端口冲突校验，包括 Inbound 之间以及与 ProxyHub Web、Clash API 的明显冲突。不执行通用操作系统端口扫描。

---

## 8. sing-box 生命周期

### 8.1 期望状态

**REQ-RUNTIME-001** ProxyHub 在内存中维护 `running` 或 `stopped` 的期望状态。人工 Start 设置为 running；人工 Stop 和配置检查失败设置为 stopped。stopped 时守护逻辑不得自动启动 sing-box。

**REQ-RUNTIME-002** 人工停止状态不跨 ProxyHub 程序重启持久化。ProxyHub 启动时，只有同时满足以下条件才自动生成、检查并启动 sing-box：

- sing-box 二进制存在；
- 数据库至少有一条能够生成有效配置的 route。

否则 Web 正常运行并保持 stopped。

### 8.2 启停与重启

**REQ-RUNTIME-003** 不同启动路径如下：

- 人工 Start：重新生成并检查配置后启动；
- 人工 Restart：停止后执行与 Start 相同的生成、检查和启动流程；
- ProxyHub 程序启动：满足自动启动条件时重新生成、检查并启动；
- Fallback 持续超时后的恢复性重启：使用当前正式配置直接重启；
- 意外退出后的守护重启：使用当前正式配置直接重启。

**REQ-RUNTIME-004** 每次 sing-box 实际启动或重启成功后，清空 Node 自动健康结果、检测状态，以及 Auto Outbound 的连续失败次数、相关计时和其他临时运行状态；Manual Outbound 恢复持久化的人工选择，Routed Auto Outbound 从 Fallback Node 初始化并从启动成功时开始记录 Fallback 持续时间。不得在 sing-box 启动前检测 Candidate 或据此决定初始 selector。

**REQ-RUNTIME-005** 每个控制周期首先检查进程状态。期望状态为 running 而进程意外退出时，控制循环使用当前正式配置直接重启本项目管理的 sing-box；重启成功后按 REQ-RUNTIME-004 重新初始化，并立即结束本控制周期，从下一周期恢复健康检测和自动切换。第一版不设置重启队列、指数退避或复杂冷却机制。

---

## 9. 节点健康检测

### 9.1 检测步骤

**REQ-HEALTH-001** 对 VMess、VLESS、Trojan 和 Shadowsocks，每次检测先执行 TCP 快检；TCP 失败立即结束并记为失败。Hysteria2 基于 QUIC/UDP，不执行 TCP 快检。

**REQ-HEALTH-002** TCP 成功后继续执行 URL 检测；Hysteria2 直接执行 URL 检测。最终健康结果以 URL 检测是否成功为准，TCP 仅用于快速排除明显不可连接节点。

**REQ-HEALTH-003** URL 检测必须通过被检测 Node 的真实代理流量，使用 sing-box Clash API delay 接口。API 返回 2xx 且 `delay > 0` 时成功，其他结果均失败。

**REQ-HEALTH-004** 所有 Node 共用一个可配置 HTTPS 测试 URL。TCP 与 URL 检测使用不同的可配置超时。

### 9.2 内存状态

**REQ-HEALTH-005** Node 运行时状态至少包含：

```text
last result: unknown / available / unavailable
checking: true / false
delay
last checked time
failure reason
```

`checking` 不覆盖上一次确定结果。状态不写入数据库，ProxyHub 或 sing-box 重启后重新检测。

**REQ-HEALTH-006** 页面人工检测可以更新页面展示的最近结果，但不参与 Auto Outbound 连续失败计数、Fallback 持续时间、自动切换或 Priority Recovery 判断。自动控制只采用对应控制步骤产生的检测结果。

**REQ-HEALTH-007** 健康结果属于 Node；连续失败次数、当前节点和故障切换状态属于 Auto Outbound。第一版不为同一 Node 被多个 Outbound 使用建立额外的跨周期缓存、有效期或复杂复用规则。

### 9.3 调度边界

**REQ-HEALTH-008** 后台控制循环按可关闭的全局扫描设置周期性检测全部 Node，并更新最近健康状态、delay、最近检测时间、failure reason 及其他页面展示和日志信息。全局扫描结果不得增加或清零 Auto Outbound 连续失败次数、触发任何 selector 切换、修改 Current Node 或 Fallback 持续时间，也不得参与 Priority Recovery；Auto Outbound 控制只采用其当前 Candidate 检测、Fallback Recovery 和 Priority Recovery 各自批次的结果。

**REQ-HEALTH-009** 页面人工检测只在 sing-box running 且当前没有检测批次时可用。stopped、未安装或已有批次运行时，页面不启动临时进程，分别提示不可检测或“检测进行中”。

**REQ-HEALTH-010** 同一时刻只运行一个检测批次；批次内部可以使用数量受限的并发。控制循环等待批次全部完成后再串行处理状态，不允许检测批次重叠。

---

## 10. Auto Outbound 故障切换

### 10.1 控制周期

**REQ-FAILOVER-001** 单一后台控制循环串行承担 sing-box 进程守护、全局 Node 健康扫描、Auto Outbound 当前节点健康检测、Candidate 故障切换、Fallback Recovery、Candidate Priority Recovery 和 Fallback 持续超时后的恢复性重启。单个检测批次内部可以使用受限并发；批次结束后的判断和切换保持串行。每个任务周期完成后固定 sleep 基础间隔，再开始下一周期，不补跑错过的墙钟周期，也不引入多后台 worker、并行状态机或独立任务队列。

**REQ-FAILOVER-002** 每个控制周期严格按以下顺序执行：

1. sing-box 进程守护；
2. 全局 Node 健康扫描到期时执行该批次；
3. 逐个处理 Routed Auto Outbound；
4. 对每个 Outbound，Current Node 不是 Fallback Node 时先执行当前 Candidate 检测和必要的故障切换，再执行到期的 Candidate Priority Recovery；周期开始处理时 Current Node 已是 Fallback Node 时，先执行 Fallback Recovery，再判断 Fallback 持续时间是否超时。

进程守护触发并成功重启，或任何 Outbound 触发恢复性重启时，本控制周期立即结束。

Auto Outbound 第一版运行状态由少量内存字段表达，至少包括 Current Node、连续失败次数、Fallback 开始时间和上次 Priority Recovery Scan 时间；状态可以由 Current Node 所处的 Candidate 优先级或是否为 Fallback 推导，不持久化或引入额外复杂状态机。

### 10.2 当前 Candidate 健康检测与切换

**REQ-FAILOVER-003** 对每个 Current Node 不是 Fallback Node 的 Routed Auto Outbound，每个控制周期检测 Current Node。只有这种当前 Candidate 自动检测参与该 Outbound 的连续失败计数：失败加一，成功清零。Fallback Recovery、Priority Recovery、全局扫描和人工检测均不得增加或清零该计数。

**REQ-FAILOVER-004** 当前 Candidate 连续失败达到阈值时：

1. 本周期通过 Clash API 立即切换到 Fallback Node；
2. 切换成功后将 Current Node 更新为 Fallback Node，清零连续失败次数，并从切换成功时开始记录 Fallback 持续时间；
3. 该 Outbound 本周期处理结束，不在同一周期执行 Fallback Recovery；
4. 同一周期有多个 Outbound 达到阈值时，控制循环仍按顺序逐个处理。

### 10.3 从 Fallback Node 恢复

**REQ-FAILOVER-005** 周期开始处理时 Current Node 已经是 Fallback Node 的 Routed Auto Outbound，每个周期检测该 Outbound 的全部 Candidate Node。检测批次不以 Fallback Node 自身为 Candidate；Fallback Node 可以由全局扫描等检测记录健康状态，用于页面展示和人工排错。

**REQ-FAILOVER-006** Candidate 检测批次结束后：

- 存在 available Candidate：立即选择人工优先级最高者切换；
- 不按 delay 排序；
- 不要求连续成功次数或最短保持时间；
- 没有 available Candidate Node：保持 Fallback Node。

成功切换到 Candidate 后清除 Fallback 持续时间，连续失败次数保持为零；不得切换到已知 unavailable Candidate。

### 10.4 Candidate Priority Recovery

**REQ-FAILOVER-007** Current Node 不是 Fallback Node、Current Candidate 不是人工优先级最高的 Candidate，并且距离上次 Priority Recovery Scan 已达到配置间隔时，只检测优先级高于 Current Candidate 的全部 Candidate Node。不得检测当前 Candidate 或优先级更低的 Candidate。

**REQ-FAILOVER-008** Priority Recovery Scan 结束后，存在 available 的更高优先级 Candidate 时，立即选择其中人工优先级最高者切换；否则保持当前 Candidate。该机制不按 delay 排序，不要求连续成功多次，不设置最短节点保持时间，也不增加或清零当前 Candidate 故障检测使用的连续失败次数。Current Candidate 已是最高优先级时不执行 Priority Recovery Scan。

### 10.5 Fallback 持续超时后的恢复性重启

**REQ-FAILOVER-009** 每个处于 Fallback 的 Routed Auto Outbound 必须先完成本周期 Fallback Recovery。完成后 Current Node 仍为 Fallback Node，且持续处于 Fallback 的时间达到配置的 Fallback Restart Timeout 时，使用当前正式配置重启整个 sing-box。触发条件不要求 Fallback Node unavailable，也不要求全部 Candidate 和 Fallback Node 均 unavailable；即使 Fallback available 而全部 Candidate unavailable，达到超时后也允许重启。

**REQ-FAILOVER-010** Fallback 持续超时重启是用于重新建立 DNS、连接和 sing-box 内部运行状态的主动恢复机制。重启成功后按 REQ-RUNTIME-004 初始化所有 Outbound；如果 Candidate 长时间无法恢复，允许系统在每次重新累计完整 Fallback Restart Timeout 后再次重启。第一版不设置指数退避、重启次数上限、复杂 cooldown 或基于 Fallback 健康状态的附加条件。

**REQ-FAILOVER-011** Fallback Recovery 必须先于超时判断。若已达到超时但本周期发现 available Candidate 并成功切换，则清除 Fallback 持续时间，本周期不执行恢复性重启。保持 Fallback 时，不停止 Inbound、不修改 Route，也不切换到已知 unavailable Candidate；一次恢复性重启会清除其他 Outbound 的临时运行状态。

### 10.6 切换失败

**REQ-FAILOVER-012** 只有 Clash API 明确确认成功后才修改内存 Current Node 和相关状态。切换失败时：

- 故障 Candidate Node 切换到 Fallback Node 失败：记录关键事件并重启 sing-box；
- Fallback Node 恢复 Candidate Node 失败：保持 Fallback Node，下周期重新检测和尝试；
- Priority Recovery 切换到更高优先级 Candidate 失败：保持当前 Candidate，后续到期时重新扫描和尝试；
- Manual 人工切换失败：保持原选择并向页面返回失败；
- 如果 sing-box 已退出，由同一串行生命周期处理完成重启，不并发执行第二个恢复动作。

**REQ-FAILOVER-013** selector 切换需要中断仍绑定旧节点的已有连接，使后续重连使用新节点。准确 sing-box 配置和能力验证在集成设计阶段完成。

---

## 11. 管理页面与认证

### 11.1 页面范围

**REQ-UI-001** 桌面页面提供 Subscription、Node、Inbound、Outbound、Route、Settings、状态、关键日志和 sing-box 管理功能。

**REQ-UI-002** 桌面页面支持刷新订阅、人工检测 Node、切换 Manual 当前节点、Start、Stop、Restart、下载日志以及人工检查和升级 sing-box。

**REQ-UI-003** 移动页面只提供整体状态、Outbound 状态、Node 健康状态和 Manual 当前节点切换，不提供结构配置、Settings、升级或完整日志管理。

### 11.2 登录

**REQ-AUTH-001** 登录使用用户名和密码。默认用户名为 `admin`，默认密码为空；密码为空时按个人部署需求跳过认证，但页面持续显示醒目安全警告。

**REQ-AUTH-002** 密码非空时，桌面页面、移动页面、全部内部 API 和日志下载都必须认证。系统提供登录和退出。

**REQ-AUTH-003** 密码只保存安全哈希，不保存或记录明文。修改用户名或密码后立即使既有会话失效并要求重新登录。

**REQ-AUTH-004** 修改类请求提供基本 CSRF 防护；会话 Cookie 至少设置 HttpOnly 和 SameSite，HTTPS 部署时设置 Secure。第一版不实现角色权限、企业级风控或复杂防暴力破解。

**REQ-AUTH-005** ProxyHub 本身不终止公网 TLS。公网访问由 Nginx、监听地址和防火墙负责，部署文档必须明确安全边界。

---

## 12. Settings、日志和默认值

### 12.1 Settings 行为

**REQ-SETTINGS-001** 所有应用设置使用单一 `data/settings.json` 文件持久化，并按 Web、Clash API、健康检测和认证等领域分组。Settings 不建立数据库表，也不使用数据库键值记录。

**REQ-SETTINGS-002** Settings 页面允许修改检测、故障切换、登录用户名和密码设置。Web 和 Clash API 的监听地址、端口不在页面修改，只能直接修改 JSON 并重启 ProxyHub。

**REQ-SETTINGS-003** ProxyHub 启动时加载 `data/settings.json`。文件不存在时，使用内置默认值创建完整文件。Settings 页面保存时必须先校验完整设置，再通过同目录临时文件原子替换正式文件，并同步更新当前进程的内存设置。

**REQ-SETTINGS-004** 通过 Settings 页面保存检测或故障设置不重启 sing-box，也不改变 selector 当前选择；系统清空健康结果、连续失败次数和相关检测临时状态，使新参数从下一控制周期生效。登录用户名和密码保存后立即生效。

**REQ-SETTINGS-005** 用户直接编辑 `data/settings.json` 时，修改只在下次 ProxyHub 启动后生效。第一版不监视文件变化，也不为手工编辑提供运行时热加载。

**REQ-SETTINGS-006** JSON 格式错误、存在未知结构或字段值非法时，ProxyHub 不得静默覆盖或使用部分配置，也不得启动 sing-box；程序应保留原文件并明确报告错误，等待用户修正后重新启动。

**REQ-SETTINGS-007** JSON 中只保存密码安全哈希，不保存明文密码。用于签名登录会话的随机 secret 不属于普通 Settings，应保存在独立密钥文件中，不在 Settings 页面显示。

### 12.2 默认值

| 设置 | 默认值 | 修改方式 |
|---|---:|---|
| 控制循环基础间隔 | 15 秒 | Settings 页面或 JSON |
| 当前节点连续失败阈值 | 3 次 | Settings 页面或 JSON |
| TCP 检测超时 | 3 秒 | Settings 页面或 JSON |
| URL 检测超时 | 5 秒 | Settings 页面或 JSON |
| 测试 URL | `https://www.gstatic.com/generate_204` | Settings 页面或 JSON |
| 单批检测最大并发数 | 10 | Settings 页面或 JSON |
| 全局 Node 周期健康扫描 | 启用 | Settings 页面或 JSON |
| 全局 Node 周期健康扫描间隔 | 600 秒 | Settings 页面或 JSON |
| Candidate Priority Recovery Interval | 60 秒 | Settings 页面或 JSON |
| Fallback Restart Timeout | 300 秒 | Settings 页面或 JSON |
| Web 监听地址 | `127.0.0.1` | JSON，重启生效 |
| Web 端口 | 8080 | JSON，重启生效 |
| Clash API 端口 | 9090 | JSON，重启生效 |
| Clash API 监听地址 | `127.0.0.1` | JSON，重启生效 |
| 登录用户名 | `admin` | Settings 页面或 JSON |
| 登录密码 | 空 | Settings 页面；JSON 只保存哈希 |

### 12.3 日志

**REQ-LOG-001** 后端文件日志记录足够的运行和排错信息。桌面页面只显示最近关键事件，不提供完整日志浏览，但允许下载日志文件。

**REQ-LOG-002** Node 切换、Fallback 持续超时、全局 Node 扫描、sing-box 启动/停止/重启、配置生成和升级属于关键事件。

**REQ-LOG-003** 第一版不实现消息推送。未来推送可以作为关键事件日志的附加处理，但不得预先引入推送平台抽象。

---

## 13. sing-box 下载、升级与部署

### 13.1 下载与升级

**REQ-UPGRADE-001** ProxyHub Web 在 sing-box 不存在时仍可运行，状态显示“未安装”并保持 stopped。用户可以人工下载官方 GitHub Release 中适用于 amd64/x86_64 的 sing-box。

**REQ-UPGRADE-002** 只有二进制不存在或 sing-box 已停止时才允许检查、下载或升级；running 时只显示本地当前版本。成功升级后不自动启动。

**REQ-UPGRADE-003** 下载或升级采用最小失败保护：

1. 下载到同一文件系统的临时文件；
2. 验证下载完成、架构正确、可执行并能读取合法版本；
3. 验证成功后原子替换正式二进制；
4. 任一步失败都保留原二进制并报告失败。

第一版不保存多版本、不自动回滚历史版本，也不后台自动升级。

### 13.2 部署

**REQ-DEPLOY-001** 第一版同时提供 Docker Compose 和 Ubuntu Python/venv 部署方式，共用同一种简单配置格式。

**REQ-DEPLOY-002** 支持 Ubuntu 20.04 及以上版本、amd64/x86_64 CPU；不要求支持 Windows、macOS、其他 Linux 发行版或 arm64。

---

## 14. 最低可靠性要求

**REQ-REL-001** Subscription 刷新、结构修改、配置生成、sing-box 启停和升级等改变状态的操作在单进程内串行执行。第一版不建立跨进程锁或分布式事务。

**REQ-REL-002** 订阅请求、解析或预览失败时原数据不变；用户确认导入后，节点更新和级联删除作为一个业务事务完成。

**REQ-REL-003** 删除 Subscription、Node、Inbound、Outbound 或 Route 前显示简单确认；涉及级联时显示受影响对象。

**REQ-REL-004** 启动或配置检查失败时，前端显示简单错误和关键事件，详细信息写入可下载日志。不建立大型结构化错误模型或专项错误页面。

**REQ-REL-005** 第一版不承诺配置更新无中断，允许人工 Stop、修改、Start 过程中出现短暂停顿。

---

## 15. 第一版明确不做

第一版不实现：

- 多用户、角色和权限管理；
- 多台 ProxyHub 主机集中管理；
- 多 sing-box 实例或多代理引擎；
- Xray、sslocal 和 TUIC；
- 面向第三方的稳定公共 API；
- 多 Web worker、多进程共享状态；
- 分布式任务队列、任务历史和任务恢复；
- 自动订阅刷新；
- 配置热重载或独立“应用配置”；
- 完整规则路由、分流规则和通用 sing-box 配置编辑器；
- 历史健康、历史延迟、流量统计和分析报表；
- 消息推送；
- sing-box 后台自动升级和复杂版本回滚；
- v1/v2 数据库、Settings、运行状态或内部 API 兼容迁移；
- 企业级高可用、复杂安全风控和所有理论异常的专项恢复机制。

---

## 16. 正式冻结前检查清单

- [ ] 产品范围、协议范围和不做范围无冲突；
- [ ] Subscription 跳过、差异确认及级联删除场景得到确认；
- [ ] Manual/Auto/Direct Outbound 行为得到确认；
- [ ] Auto Outbound 正常、故障、Fallback Recovery、Candidate Priority Recovery 和 Fallback 超时重启流程得到确认；
- [ ] 人工检测与 Auto Outbound 自动控制边界得到确认；
- [ ] Start、Restart、守护重启和首次启动行为得到确认；
- [ ] 页面、认证、Settings、日志和升级边界得到确认；
- [ ] 至少完成本文第 3 节场景的验收描述；
- [ ] 后续数据模型和状态机设计不需要自行补充新的业务规则。

全部通过后，将本文标记为 `Requirements v1.0`，再进入数据模型和运行时状态机设计。
