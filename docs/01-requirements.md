# ProxyHub 个人版第一版需求规范

> 文档版本：v0.2（评审修订稿）

> 文档状态：待评审

> 更新日期：2026-09-03

> 适用范围：ProxyHub 新版本第一版

## 0. 文档说明

本文描述 ProxyHub 第一版“应该做什么”，是后续数据模型、状态机、sing-box 集成、页面、API 和验收设计的需求基准。

## 1. 产品目标与实施边界

### 1.1 产品目标

**REQ-GEN-001** ProxyHub 是供单人使用、自行部署的本地代理网关管理工具。

**REQ-GEN-002** 系统接收机场订阅节点和用户自建节点，将远程节点组织为本地代理入站，供本机或其他设备使用。

**REQ-GEN-003** 系统以 sing-box 作为唯一代理引擎，提供节点健康检测、自动故障恢复、手动节点切换及 sing-box 生命周期管理。

### 1.2 第一版原则

**REQ-GEN-004** 第一版服务个人家庭实际使用，不以公共服务、多用户平台、企业部署或通用代理管理平台为目标。

**REQ-GEN-005** 第一版优先保证主要行为简单、确定、可排错，不为低概率异常建立复杂恢复状态、分布式任务、历史任务或企业级高可靠机制。

**REQ-GEN-006** 第一版面向单一可信用户和正常操作路径，只实现保护核心数据与运行流程所需的基本防护，包括必要的输入校验、业务不变量校验、关键文件原子替换、生命周期串行化和错误日志。除非具体需求另有明确规定，不为恶意调用、绕过正常页面或内部 API 的异常请求、人工直接修改数据库或正式配置、不支持环境、低概率边缘情况或“以后可能需要”的能力增加复杂兼容、恢复、重试、回滚、冗余备份、抽象层或高可靠机制；设计和实现应选择满足当前明确需求的最简单方案。具体需求已经规定的事务、失败保护、一致性或恢复规则不受本条削弱。

**REQ-GEN-007** 系统只支持单 ProxyHub 实例、单 Web 进程、单 sing-box 进程和单后台控制循环。同一数据目录不得同时运行多个 ProxyHub 实例。

---

## 2. 业务模型与基本约束

### 2.1 核心关系

Subscription 和用户自建配置用于产生 Node。

Node 可以被 MANUAL 和 AUTO 使用；DIRECT 不包含 Node。一个 MANUAL/AUTO 可以包含多个 Node。

Inbound 表示本地代理入口，Outbound 表示流量出口。Outbound 分为 DIRECT、MANUAL 和 AUTO 三种类型。

用户分别选择一个 Inbound 和一个 Outbound，创建一条 Route，用于建立该 Inbound 到该 Outbound 的流量映射。

### 2.2 名词

- **Subscription**：用户保存的机场订阅及其 Filter/Exclude 设置。

- **Node**：一个可生成 sing-box 远程出站的代理节点，来源为订阅或自建。

- **Inbound**：向本机或其他设备提供服务的本地监听入口。

- **Outbound**：所有流量出口的统称，type 只有 `direct`、`manual` 和 `auto` 三种。

- **DIRECT**：`type = direct` 的系统内置 Outbound，全局唯一、只读、不包含 Node 且不保存数据库记录，可被 Route 显式选择。

- **MANUAL**：`type = manual` 的用户 Outbound，保存于数据库并包含 Node Pool，由用户人工选择并持久化 Current Node，不执行自动故障切换。

- **AUTO**：`type = auto` 的用户 Outbound，保存于数据库并包含 Node Pool，由后台控制循环管理运行时 Current Node，并在节点故障时自动恢复代理能力。

- **MANUAL/AUTO**：同时指 MANUAL 和 AUTO，不包括 DIRECT。

- **Route**：一个 Inbound 到一个 Outbound 的明确流量映射；目标 Outbound 可以是 DIRECT、MANUAL 或 AUTO。

- **Node Pool**：一个 MANUAL 或 AUTO 包含的有序 Node 集合；每个 Node 在该 Pool 中具有连续、唯一的 `1...N` priority。

- **Candidate Node**：AUTO 的 Node Pool 中除 Fallback Node 外的 Node。Candidate 直接使用其在完整 Node Pool 中的 priority 参与自动择优和 Priority Recovery，不单独重新编号。

- **Fallback Node**：AUTO 中明确指定的备用 Node。Fallback Node 保留自身 Node Pool priority 用于页面展示和配置顺序，但不参与 Candidate 自动择优和 Priority Recovery。

- **Current Node**：MANUAL 或 AUTO 当前在 sing-box selector 中选择的 Node。MANUAL 的 Current Node 持久化；AUTO 的 Current Node 只保存在运行时内存中。

- **Routed AUTO**：至少被一条 Route 引用的 AUTO。该名称只表示 Route 引用关系，不表示 sing-box 当前一定处于 running 状态。

### 2.3 全局不变量

**REQ-MODEL-001** 每条 Route 必须引用一个 Inbound 和一个 Outbound。一个 Inbound 被某条 Route 引用后，不能再被其他 Route 引用；一个 Outbound 可以同时被多条 Route 引用。Outbound 的 type 可以是系统内置的 `direct`，也可以是数据库中现存的 `manual` 或 `auto`。

**REQ-MODEL-002** 多条 Route 引用同一个 MANUAL 或 AUTO 时，共享该 MANUAL/AUTO 的 Node Pool、priority、Current Node 和运行状态。DIRECT 不具有 Node Pool、Current Node 或运行时节点健康状态。

**REQ-MODEL-003** Node 是全局实体。同一个 Node 可以加入多个 MANUAL 或 AUTO，但在同一个 Node Pool 中只能出现一次。每个 MANUAL 或 AUTO 正常保存时必须至少包含两个不同 Node。

**REQ-MODEL-004** 数据库只持久化 Subscription、Node、Inbound、MANUAL/AUTO 和 Route，以及 Outbound type、Node Pool priority、MANUAL 的 Current Node 和 AUTO 的 Fallback Node 等业务数据；数据库中的 Outbound type 只能是 `manual` 或 `auto`，DIRECT 不保存数据库记录。应用 Settings 持久化在独立的 `data/settings.json` 文件中。Node 健康结果、TCP/URL delay、失败计数和 AUTO 的 Current Node 等运行时状态只保存在内存中。

---

## 3. 核心使用场景

### 3.1 首次安装与配置

```text

启动 ProxyHub Web

→ sing-box 未安装或没有任何有效 Route，管理状态保持 stopped

→ 用户下载 sing-box

→ 添加订阅或自建节点

→ 创建 MANUAL/AUTO、Inbound 和 Route；Route 可明确选择 DIRECT、MANUAL 或 AUTO

→ 用户点击 Start

→ 生成并检查配置

→ 检查成功后启动 sing-box

```

只包含目标为 DIRECT 的 Route 的配置同样属于有效配置；没有 Route 的 Inbound 不写入 sing-box 配置，也不对外监听。

### 3.2 正常运行

```text

sing-box 实际启动或重启成功

→ 已生效的 AUTO 初始选择 Fallback Node

→ 清空 AUTO 的临时运行状态并开始记录 Fallback 持续时间

→ 下一控制周期扫描全部 Candidate Node

→ 选择可用 Candidate 中 priority 最高者

→ 后续每个控制周期检测 Current Candidate

→ Current Candidate 不是最高 priority Candidate 时，按独立间隔扫描更高 priority Candidate

```

### 3.3 当前节点故障恢复

```text

当前 Candidate 连续检测失败达到阈值

→ 本周期立即切换 Fallback Node

→ 本 AUTO 本周期处理结束

→ 下一个控制周期扫描全部 Candidate Node

→ 有可用 Candidate：切换到 priority 最高的可用节点

→ 没有可用 Candidate：保持 Fallback Node

```

### 3.4 Fallback 持续超时恢复

```text

AUTO 的 Current Node 为 Fallback Node

→ 每个控制周期先扫描全部 Candidate Node

→ 有可用 Candidate：切换到 priority 最高的可用节点并结束 Fallback 状态

→ 没有可用 Candidate：保持 Fallback Node

→ 持续处于 Fallback 达到配置超时时间：重启整个 sing-box

→ 清空运行时状态并重新执行初始选择

```

### 3.5 同步订阅节点

```text

管理状态 stopped

→ 用户请求同步订阅节点

→ 请求、解析、过滤和校验

→ 跳过无效或不支持的节点

→ 至少存在一个有效节点时生成差异预览

→ 同时展示节点变化、Current/Fallback 自动替换和级联删除影响

→ 用户确认：原子更新数据

→ 用户取消：不修改任何数据

```

Subscription 新增、修改、删除和同步订阅节点在 running 时均禁止，统一遵循 REQ-CONFIG-001。REQ-SUB-004 规定的刷新订阅信息不属于同步订阅节点，running 和 stopped 时均允许，且不得改变任何 Node。

### 3.6 人工修改配置

```text

用户停止 sing-box

→ 新增、修改、删除 Subscription 或同步订阅节点，或修改 Node、Inbound、MANUAL/AUTO 的结构、type、Node Pool、priority、Fallback/Current 角色或 Route

→ 用户再次点击 Start

→ 重新生成并检查完整配置

→ 成功后启动

```

### 3.7 sing-box 意外退出

```text

管理状态为 running

→ 控制循环发现 sing-box 已退出

→ 从最新数据库重新生成完整配置并执行 sing-box check

→ 检查失败：保持管理状态 running，记录错误并在后续控制周期继续恢复

→ 检查成功：原子替换正式配置并启动

→ 启动失败：保持管理状态 running，记录错误并在后续控制周期继续恢复

→ 启动成功：清空运行时健康及切换状态

→ 已生效的 MANUAL 恢复持久化的 Current Node，AUTO 从 Fallback Node 重新初始化

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

既有 parser 和 sing-box 映射只能作为上述五种协议字段的参考，不能隐式扩大协议范围。

**REQ-NODE-002** Shadowsocks 节点需要支持 sing-box 自身可用的 obfs 能力，不安装或管理额外 obfs 二进制。

**REQ-NODE-003** Reality、uTLS fingerprint、WebSocket、gRPC 和 HTTP/2 等字段组合的准确范围，在 sing-box 集成设计中形成字段矩阵和验证样例，但不得超出上述五种协议。

### 4.2 自建节点

**REQ-NODE-004** 用户可以逐项填写协议参数创建自建节点，也可以粘贴一条受支持的分享 URI，由页面解析并回填表单。第一版不提供多条 URI 或文件批量导入。

**REQ-NODE-005** 自建节点允许查看、修改和删除，并可以纳入 REQ-HEALTH-006 规定的人工检测。

### 4.3 保存校验

**REQ-NODE-006** Node 只有在必填字段、端口范围、协议字段组合和 sing-box 配置映射通过校验后才能保存或导入。所有已保存的全局 Node 都必须能够由应用映射器生成字段结构完整的 sing-box Remote Outbound 配置片段。Node 保存阶段不组装完整配置，也不单独调用 `sing-box check`；对象间引用、tag、Route、监听冲突和当前 sing-box 版本兼容性统一在生成完整配置并启动时校验。

**REQ-NODE-007** 凭据、UUID、密码、密钥、分享 URI、完整 Subscription URL 和包含上述内容的原始 parser 输入不得写入日志，也不得在 Subscription 同步或删除的差异预览中显示原文。差异预览只展示确认业务变化所需的 Node name、来源、协议类型、变化类型、脱敏后的字段类别和失败原因；底层 HTTP、parser 或 sing-box 错误在记录和展示前必须移除上述敏感内容。

---

## 5. 配置修改与生效

### 5.1 结构配置修改限制

**REQ-CONFIG-001** 系统将以下操作统一定义为结构配置写操作；除本文明确规定的在线操作外，结构配置写操作只允许在管理状态为 `stopped` 时执行：

- Subscription 新增、修改、删除和同步订阅节点；
- Node、Inbound 和 Route 的新增、修改和删除；
- MANUAL/AUTO 的新增和删除，以及名称、type、Node Pool、priority、AUTO Fallback Node 和通过结构编辑修改 MANUAL Current Node；
- 其他会改变下一次生成的 sing-box 完整配置结构、对象定义或初始选择的业务数据修改。

管理状态为 `running` 时统一禁止上述操作。即使 sing-box 实际进程已经退出或恢复失败，只要管理状态仍为 `running`，限制继续有效，用户必须先执行 Stop。DIRECT 始终为只读系统对象，不允许修改。

**REQ-CONFIG-002** 管理状态为 `running` 时允许执行以下非结构配置操作：

- 查看状态和日志；
- 刷新 Subscription 的流量、有效期等信息；
- 按 REQ-HEALTH-006 人工检测 Node；
- 按 REQ-OUTBOUND-007 在线切换 MANUAL Current Node；
- 修改 12.2 明确支持在线生效的 Settings；
- Stop；
- Restart。

上述“允许”表示操作不受结构配置冻结规则禁止；人工检测仍要求 sing-box 实际进程正在运行，MANUAL Current Node 在线切换仍要求目标 MANUAL 已写入当前配置、sing-box 实际进程正在运行且 Clash API 可用。Subscription 信息刷新只更新展示所需的 Subscription 元信息，不执行 Node parser，也不增加、修改或删除任何 Node，因此不属于结构配置写操作。

### 5.2 修改与生效

**REQ-CONFIG-003** 在 `stopped` 状态进行结构配置写操作时，只更新数据库，不生成、检查或替换 sing-box 配置，也不自动启动 sing-box。结构配置在下一次从最新数据库成功生成完整配置并实际启动 sing-box 时生效；该生成可能由人工 Start、Restart、ProxyHub 自身启动时的自动启动或运行期间的进程守护恢复触发。

MANUAL Current Node 在线切换是结构配置冻结规则的明确例外。MANUAL Current Node 同时具有数据库中的持久化选择和 sing-box selector 的运行时实际选择，具体修改、在线切换、持久化和页面展示规则由 REQ-OUTBOUND-007 规定。

Settings、Subscription 信息刷新和 Node 检测分别按各自章节规定写入 Settings 文件、Subscription 元信息或运行时展示状态，不适用“结构配置只写数据库”的规则。

系统不提供独立 Apply 按钮，不建立 Pending Config、待生效状态或配置版本状态机。

### 5.3 配置生成

**REQ-CONFIG-004** 每次需要实际启动 sing-box 时，统一执行以下完整配置生成流程：

```text

读取数据库

→ 生成临时完整配置

→ 执行 sing-box check

→ 成功：替换正式配置，启动 sing-box 并确认进程正在运行，再按本次启动来源更新管理状态

→ 失败：数据库不回滚；管理状态按本次启动来源的运行状态规则处理

```

**REQ-CONFIG-005** 完整配置包含：

- 所有合法的全局 Node 独立出站，包括未被任何 MANUAL/AUTO 引用的 Node；

- 被至少一条 Route 引用的 MANUAL/AUTO；

- Route 使用的系统内置 DIRECT；

- 仅被 Route 引用的 Inbound；

- 现存 Route 映射；

- 固定监听 `127.0.0.1:9090` 的 Clash API。

MANUAL/AUTO、DIRECT、Node 和 Route 到 sing-box 配置对象、tag 及字段的具体映射由 sing-box 模块设计规定。实现必须满足本文关于 Node Pool priority、MANUAL 的 Current Node、AUTO 的 Fallback Node、启动初始化、连接中断和 DIRECT Route 的业务要求，不得由历史运行状态覆盖 MANUAL/AUTO 的初始化选择。

**REQ-CONFIG-006** 系统保留上一份可用正式配置供人工排错，但新配置检查失败后不自动恢复或启动旧配置。

**REQ-CONFIG-007** 对会写入配置的 Inbound 执行基本监听地址和端口冲突校验，包括 Inbound 之间以及与 ProxyHub Web、Clash API 的明显冲突。不执行通用操作系统端口扫描。

---

## 6. Subscription 管理

### 6.1 添加、修改与请求

**REQ-SUB-001** 系统允许维护多个 Subscription。同步订阅节点只在用户从页面明确发起时执行，不执行后台定时同步。新建 Subscription 后允许暂时不包含任何 Node，直到用户首次明确执行同步订阅节点。

修改 Subscription URL、Filter 或 Exclude 只更新 Subscription 自身配置，不请求或解析订阅，也不增加、修改或删除已有 Node。新的 URL、Filter 和 Exclude 只在下一次用户明确执行同步订阅节点时用于 Node 同步；修改 Subscription 不等于自动同步 Node。

**REQ-SUB-002** 第一版 Subscription URL 只接受具有正常有效证书的 HTTPS 地址，不支持 HTTP、局域网订阅地址、自签名证书或忽略证书校验。

**REQ-SUB-003** Subscription 请求使用程序内置、固定的 Clash 兼容 User-Agent 和请求头，不允许为单个 Subscription 配置自定义请求头。

**REQ-SUB-004** 系统可以读取并显示 Subscription 提供的已使用流量、总流量、到期时间等元信息。用户可以在管理状态为 `running` 或 `stopped` 时刷新 Subscription 信息；刷新使用当时保存的 Subscription URL，只更新 Subscription 元信息，不执行 Node parser，也不同步、增加、修改或删除任何 Node。

Subscription 新增、修改、删除和同步订阅节点的运行状态限制统一由 REQ-CONFIG-001 规定，本章不重复定义。

### 6.2 Filter 与 Exclude

**REQ-SUB-005** Filter/Exclude 只匹配 Node 的 `name`：

- 忽略大小写；
- 关键词使用逗号或换行分隔，并去除关键词自身首尾空白及空项；
- 多个 Filter 关键词为 OR；Filter 为空表示不过滤；
- 多个 Exclude 关键词为 OR；
- 同时命中时 Exclude 优先；
- 不支持正则表达式、自动地区分组或复杂筛选规则。

### 6.3 解析、匹配与跳过

**REQ-SUB-006** 同步订阅节点时依次执行 Subscription 请求、parser、Filter/Exclude、Node 校验和差异计算。无效节点和不支持协议节点全部跳过；预览需要显示跳过数量、可安全显示的节点标识和脱敏原因。只要过滤后至少剩一个合法节点，就允许进入差异确认。

**REQ-SUB-007** 如果请求失败、订阅整体格式无法识别、没有任何合法节点，或经过 Filter/Exclude 后结果为空，本次同步失败，不产生可确认结果，原数据不变。

**REQ-SUB-008** 同步同一 Subscription 的 Node 时，以“Subscription + parser 产出的 `name` 完整内容”作为 Node 身份判断基础。`name` 匹配区分大小写，不自动修剪、改写或进行 Unicode 归一化：

- name 完全相同视为同一 Node；
- name 相同而其他字段变化视为修改；
- name 变化视为删除旧 Node 并新增新 Node；
- 不同 Subscription 允许存在相同 name；
- 同一 Subscription 出现完全相同的重复 name 时，由于身份不明确，本次同步整体失败。

系统不根据地址、端口、UUID 或其他协议字段猜测两个不同 name 的 Node 是否只是被重命名。

### 6.4 差异确认与事务

**REQ-SUB-009** 同步请求成功解析后，页面显示新增、修改、删除和跳过 Node 的数量及脱敏明细；用户确认前不得修改数据库。用户只能确认或取消整个差异结果，不提供逐条选择导入或删除的能力。

**REQ-SUB-010** 差异预览必须同时显示 Node 删除引起的 MANUAL Current Node 或 AUTO Fallback Node 自动替换、被删除的 MANUAL/AUTO 和被删除的 Route。用户确认提交时，后端必须取得运行控制锁，再次确认管理状态为 `stopped`，并确认预览所依据的相关数据没有变化；状态或数据已经变化时拒绝提交并要求重新生成预览。校验通过后，在一个业务事务中完成 Subscription（适用时）、Node、Outbound 和 Route 的全部相关变更；用户取消时任何数据都不改变。

**REQ-SUB-011** 被跳过的 Node 不进入新订阅结果。因此它可能使原有同名 Node 出现在删除预览中；最终是否导入及执行自动替换、级联删除由用户查看完整预览后确认。

**REQ-SUB-012** Subscription Node 为只读，不能人工修改协议参数；其内容只能通过同步订阅节点更新。自建 Node 与 Subscription Node 在页面中必须显示不同来源。

**REQ-SUB-013** 明确删除 Subscription 时，先展示其全部 Node 及 Current/Fallback 自动替换、MANUAL/AUTO 删除和 Route 删除等完整级联影响，用户确认时执行与 REQ-SUB-010 相同的状态复核、数据变化校验和事务处理。

---

## 7. Inbound、Outbound 与 Route

### 7.1 Inbound

**REQ-INBOUND-001** 系统允许创建任意数量的 Inbound，支持 HTTP、SOCKS、Mixed、Shadowsocks 和 VMess。

**REQ-INBOUND-002** 每个 Inbound 独立定义名称、监听协议、监听地址、监听端口和该协议所需的认证参数。Mixed 在同一端口兼容 HTTP 和 SOCKS。

### 7.2 Outbound 通用约束

**REQ-OUTBOUND-001** 每个 MANUAL/AUTO 独立定义名称，由用户创建并保存于数据库，其 Node Pool 由全局 Node 组成。

**REQ-OUTBOUND-002** 每个 MANUAL 和 AUTO 必须始终至少包含两个不同 Node。Node 是全局对象，可以被多个 MANUAL/AUTO 复用，但在同一个 Node Pool 中只能出现一次。用户正常创建或编辑 Node Pool 时，少于两个 Node 不允许保存；全局 Node 删除、Subscription 删除或同步订阅节点造成不足两个 Node 时，按 REQ-ROUTE-006 和 REQ-ROUTE-007 执行预览及级联删除。

**REQ-OUTBOUND-003** MANUAL/AUTO 的 Node Pool 是有序 Node 集合；每个 Node 都必须具有连续、唯一的 `1...N` priority，数值越小、优先级越高。页面按 priority 数值升序显示，`priority = 1` 的 Node 显示在最前；priority 的运行用途由 Outbound type 决定。

**REQ-OUTBOUND-004** 新建 MANUAL/AUTO 时，前端必须提交确定的 Node 顺序：逐个选择 Node 时按选择先后排序；一次同时选择多个 Node 时按 Node name 排序，name 相同时按 Node 的稳定标识排序。后端按前端提交顺序生成 priority。后续调整顺序时，保存后重新整理为连续、唯一的 `1...N` priority；修改 priority 不改变 MANUAL 的持久化 Current Node 或 AUTO 的 Fallback Node，也不自动启动 sing-box。下次启动使用新的 priority；AUTO 启动后先以 Fallback Node 作为 Current Node，下一控制周期再按新 priority 执行 Fallback Recovery。Current Candidate 已经是最高 priority Candidate 时不执行 Priority Recovery。

**REQ-OUTBOUND-005** MANUAL 的 Current Node 和 AUTO 的 Fallback Node 必须属于各自 Node Pool。正常编辑 Node Pool 时，如果移除 MANUAL 的 Current Node 或 AUTO 的 Fallback Node，但仍保留至少两个 Node，则以保存后 priority 最高的 Node 自动替代。Current Node 发生运行时切换时，必须中断仍绑定旧节点的已有入站连接，使后续重连使用新的 Current Node；具体 sing-box 配置映射由模块设计规定。

### 7.3 MANUAL/AUTO

**REQ-OUTBOUND-006** 用户新建的 Outbound type 只能是 `manual` 或 `auto`，默认为 `manual`。用户可以在 MANUAL 与 AUTO 之间修改 type，运行状态限制统一遵循 REQ-CONFIG-001。修改 type 只改变运行策略，不增加、删除或重新排序 Node。DIRECT 不可转换为 MANUAL/AUTO，MANUAL/AUTO 也不可转换为 DIRECT。

**REQ-OUTBOUND-007** MANUAL 不执行自动故障切换。priority 只用于页面展示和配置中的 Node 顺序；新建 MANUAL 时不要求用户指定 Current Node，保存后 `priority = 1` 的 Node 自动成为初始持久化 Current Node。

MANUAL Current Node 持久化在数据库中。管理状态为 `stopped` 时，用户可以通过结构编辑修改持久化 Current Node，该操作只更新数据库，不生成或修改 sing-box 配置。生成 sing-box 完整配置时，系统从数据库读取 Current Node，并将其设置为对应 selector 的默认节点；页面在 `stopped` 时显示数据库中保存的 Current Node。

MANUAL 被 Route 引用并已写入当前 sing-box 配置时，用户可以在管理状态为 `running`、sing-box 实际进程正在运行且 Clash API 可用时人工在线切换 Current Node。系统先通过 Clash API 修改 selector，只有 Clash API 明确确认成功后才将新选择持久化到数据库；切换失败时数据库保持原值，并在页面提示失败。sing-box 正常运行时，页面通过 Clash API 查询并显示 selector 的运行时 Current Node，不使用数据库值推断当前实际选择；Clash API 不可用时，页面将运行时 Current Node 显示为不可用，数据库中的持久化 Current Node 仍作为下一次生成配置时的默认选择。人工在线切换不改变 priority。

**REQ-OUTBOUND-008** 新建 AUTO 时不要求用户指定 Fallback Node，保存后 `priority = 1` 的 Node 自动成为 Fallback Node；用户后续可以手动修改，运行状态限制统一遵循 REQ-CONFIG-001。除 Fallback Node 外的其他 Node 全部是 Candidate Node。Fallback Node 的 priority 只用于页面展示和配置顺序，不参与 Candidate 自动择优；Candidate 按 priority 执行自动选择和 Candidate Priority Recovery。

**REQ-OUTBOUND-009** AUTO 的运行时 Current Node 完全由后台控制循环管理，不持久化，用户不能临时人工切换或锁定。只有被 Route 引用的 AUTO 才执行 AUTO 控制；每次 sing-box 实际启动或重启成功后，其 Current Node 从 Fallback Node 初始化。

**REQ-OUTBOUND-010** 将 type 从 `manual` 改为 `auto` 时，原持久化 Current Node 直接作为 Fallback Node；将 type 从 `auto` 改为 `manual` 时，原 Fallback Node 直接作为持久化 Current Node，修改前 AUTO 的运行时 Current Node 不保留。修改 type 时保留原 Node Pool 和全部 priority，不要求用户重新选择 Node 或排序，并清除该 MANUAL/AUTO 的临时控制状态。

### 7.4 Route

**REQ-ROUTE-001** Route 只表达一个 Inbound 的流量目标，不提供规则分流或额外“服务”业务层。每条 Route 必须引用一个 Inbound 和一个 Outbound；目标 Outbound 可以是系统内置 DIRECT，也可以是数据库中现存的 MANUAL 或 AUTO。不得以目标缺失、空引用或无效引用表示 DIRECT。

**REQ-ROUTE-002** 一个 Inbound 最多被一条 Route 引用；一个 Outbound 可以被零条、一条或多条 Route 引用。多条 Route 引用同一个 MANUAL/AUTO 时，共享其 Node Pool、Current Node 和运行状态；任意数量的 Route 可以选择系统内置 DIRECT。

**REQ-ROUTE-003** 前端和内部 API 使用稳定的系统标识表示 DIRECT；创建或修改 Route 时，该标识可以作为合法的 Outbound 引用。

**REQ-ROUTE-004** 未被 Route 引用的 Inbound 和 MANUAL/AUTO 只保存于数据库，不生成其对应的 Inbound 或 MANUAL/AUTO 运行时配置；被 Route 引用的对象才生成对应配置。Route 选择 DIRECT 时，相关 Inbound 和系统内置 DIRECT 正常写入配置并对外监听，流量直接访问目标地址。DIRECT 的具体 sing-box 配置映射由模块设计规定。

**REQ-ROUTE-005** 删除 Inbound、MANUAL 或 AUTO 时，一并删除引用它的 Route。删除 MANUAL/AUTO 不得把原 Route 自动或静默改为 DIRECT；DIRECT 不可删除。

**REQ-ROUTE-006** 删除一个或多个 Node 时，以本次操作全部 Node 删除完成后的剩余 Node Pool 为准，对所有受影响的 MANUAL/AUTO 按以下规则处理：

- MANUAL/AUTO 剩余至少两个 Node：保留其余 Node 的相对顺序，重新整理为连续、唯一的 `1...N` priority；
- MANUAL 的持久化 Current Node 被删除时，以剩余 Node 中 priority 最高者作为新的持久化 Current Node；
- AUTO 的 Fallback Node 被删除时，以剩余 Node 中 priority 最高者作为新的 Fallback Node；
- MANUAL/AUTO 剩余不足两个 Node：删除该 MANUAL/AUTO，并继续删除引用它的全部 Route。

**REQ-ROUTE-007** 人工删除一个或多个 Node、删除 Subscription，以及同步订阅节点删除 Node，都使用相同的级联规则。执行前必须向用户展示完整影响，包括 Current/Fallback Node 的自动替换、MANUAL/AUTO 删除和 Route 删除；用户确认后，在同一个业务事务中完成 Subscription（适用时）、Node、Outbound 和 Route 的全部变更。

**REQ-ROUTE-008** 正常编辑 MANUAL/AUTO 的 Node Pool 时，用户必须保持至少两个 Node；如果移除 Current/Fallback Node 但仍满足最少节点数，则按 REQ-OUTBOUND-005 自动替换。由全局 Node 删除、Subscription 删除或同步订阅节点造成的 Node Pool 缩减不按普通编辑拒绝保存，而按 REQ-ROUTE-006 和 REQ-ROUTE-007 执行预览、替换和级联删除。

---

## 8. ProxyHub 运行任务

### 8.1 sing-box 运行状态

**REQ-RUNTIME-001** ProxyHub 分别维护 sing-box 的管理状态和实际进程状态。管理状态只有 `running` 和 `stopped` 两种，配置修改限制按管理状态判断；页面同时展示实际运行、已退出或启动失败等进程状态。

- Start 开始后管理状态仍为 `stopped`；数据库中没有 Route 时 Start 失败，提示用户至少创建一条 Route，只有 DIRECT Route 时允许启动；存在 Route 时从最新数据库生成完整配置并执行 `sing-box check`，只有检查通过、sing-box 启动成功并确认进程正在运行后才进入 `running`，任一步失败都保持 `stopped`；
- Stop 停止 sing-box，并停止进程守护和 AUTO 控制，进入 `stopped`；
- 用户发起的 Restart 严格等于在同一次运行控制加锁操作中依次执行 Stop 和 Start；检查或启动失败时保持 `stopped`，不恢复或自动启动旧进程；
- 管理状态为 `running` 但实际进程已退出或恢复失败时，仍禁止结构修改；
- `stopped` 状态不执行进程守护或 AUTO 控制；
- 手动 Stop 状态不跨 ProxyHub 自身重启持久化；
- 不增加“待应用配置”或其他管理状态。

### 8.2 ProxyHub 启动

**REQ-RUNTIME-002** ProxyHub 自身启动时，只有同时满足以下条件才自动生成、检查并启动 sing-box：

- sing-box 二进制存在；
- Settings 已成功加载并通过校验；
- 数据库中至少存在一条可以生成有效配置的 Route。

Route 的目标可以是 DIRECT、MANUAL 或 AUTO。没有 Route 时不启动 sing-box；只有 DIRECT Route 时仍属于合法配置，可以正常启动。

Settings 已成功加载但其他条件不满足、配置检查失败或进程启动失败时，ProxyHub Web 仍正常运行，sing-box 管理状态保持 `stopped`。Settings 文件异常时按 REQ-SETTINGS-006 终止 ProxyHub 启动。

### 8.3 sing-box 启动和重启后的状态

**REQ-RUNTIME-003** 每次 sing-box 实际启动或重启成功后，ProxyHub 都将其视为一次新的运行周期，清除并重新初始化全部既有运行时状态，包括：

- 所有 Node 的健康状态、tcp delay、url delay、last checked time 和 failure reason；
- AUTO 的 Current Node、连续失败次数、Fallback 持续时间和 Priority Recovery 计时；
- 其他仅存在于内存中的检测和控制状态。

重新初始化时：

- 被 Route 引用的 MANUAL 使用数据库中持久化的 Current Node；
- 被 Route 引用的 AUTO 使用其 Fallback Node 作为新的 Current Node；
- AUTO 的 Fallback 持续时间从零开始累计；
- 不在启动前检测 Candidate，也不根据历史健康状态改变初始选择。

不尝试恢复 sing-box 重启前的 AUTO 运行状态。

```text
sing-box 启动或重启成功
          ↓
所有运行时状态清零
          ↓
MANUAL 恢复持久化 Current Node
AUTO 回到 Fallback Node
          ↓
下一控制周期重新开始检测
```

### 8.4 后台控制循环

**REQ-RUNTIME-004** ProxyHub 只运行一个后台控制循环，不建立任务队列、多 worker、并行状态机或独立调度器。

每个控制周期严格按以下顺序执行：

1. sing-box 进程守护；
2. AUTO 故障切换。

如果进程守护或 AUTO 故障切换触发 sing-box 重启，本控制周期立即结束。一个正常控制周期完成后，等待配置的基础间隔，再开始下一个周期；不补跑因为任务执行时间而错过的周期。

### 8.5 调度流程

后台控制循环依次执行两个主要任务：

```text
控制周期开始
      ↓
1. 进程守护
      ├── sing-box 已退出
      │       ↓
      │   从最新数据库生成、检查并启动 sing-box
      │       ├── 成功 → 重置全部状态 → 本周期结束
      │       └── 失败 → 记录错误 → 本周期结束
      ↓
2. AUTO 故障切换
      ├── 逐个处理 Routed AUTO
      ├── 具体流程遵循第 10 章
      └── AUTO 处于 Fallback 的持续时间超时
              ↓
          按 REQ-FAILOVER-010 主动重启 sing-box
              ├── 成功 → 重置全部状态 → 本周期结束
              └── 失败 → 记录错误 → 本周期结束
      ↓
等待基础控制间隔
      ↓
下一控制周期
```

统一遵循以下原则：

```text
一个控制循环
运行控制整体串行
sing-box 每次启动或重启成功后，所有运行状态全部重置
```

### 8.6 进程守护

**REQ-RUNTIME-005** 当管理状态为 `running` 时，每个控制周期首先检查 sing-box 是否仍在运行。

sing-box 正常运行时，继续执行本周期后续任务。发现 sing-box 意外退出时：

1. 从最新数据库生成临时完整配置并执行 `sing-box check`；
2. 检查成功后原子替换正式配置并启动 sing-box；
3. 启动成功后按 REQ-RUNTIME-003 清空并重新初始化全部运行时状态；
4. 本控制周期立即结束；
5. 下一控制周期重新开始 AUTO 检测。

配置检查、进程启动或 AUTO 故障切换触发的自动重启失败时，记录错误，保持管理状态为 `running` 并结束本周期；下一控制周期由进程守护再次尝试恢复。需要修改配置时，用户必须先执行 Stop。

第一版不记录连续崩溃次数，不执行指数退避，也不建立复杂进程恢复策略。

### 8.7 AUTO 故障切换任务

**REQ-RUNTIME-006** 进程守护确认管理状态为 `running`、sing-box 实际进程正在运行且 Clash API 可用后，逐个处理所有 Routed AUTO，具体检测、切换和恢复规则遵循第 10 章。进程守护未恢复成功时，本周期不执行 AUTO 检测。

AUTO 触发 sing-box 重启时，本控制周期立即结束。Fallback 持续超时按 REQ-FAILOVER-010 处理；切换失败需要重启时按 REQ-FAILOVER-011 处理。

### 8.8 运行控制锁

**REQ-RUNTIME-007** 系统使用一把进程内运行控制锁，串行化后台控制、sing-box 生命周期和结构配置写操作，不建立任务队列或复杂调度机制。

- 后台控制周期从进程守护开始，到全部 Routed AUTO 的检测、判断和切换处理结束，全程持有该锁；
- Start、Stop、Restart、结构配置写操作、MANUAL Current Node 人工切换、sing-box 下载或升级替换以及后台故障恢复重启使用同一把锁；
- 结构配置写操作取得锁后再次确认管理状态为 `stopped`，避免 Start 执行期间修改数据库；
- Restart 在一次持锁期间依次完成 Stop 和 Start，中间不释放锁，也不允许插入结构配置修改；
- Stop 或 Restart 到来时，如果后台控制周期正在执行，则等待该周期完整结束，不取消正在执行的 AUTO 检测；
- Settings 保存和人工检测不持有运行控制锁；
- 多个生命周期请求同时发生时，按取得锁的顺序执行，不实现任务取消、请求合并或任务队列。

### 8.9 检测并发

**REQ-RUNTIME-008** 删除后台自动全局 Node 周期扫描。AUTO 检测和人工检测不在全局范围内互斥，可以同时执行。

每个 AUTO 检测过程和每个人工检测请求分别受 Settings 中 `Max Concurrency` 限制；单 Node 人工检测请求只包含一个 Node。第一版不限制用户同时发起的人工检测请求数量，不保证系统级检测总并发上限，也不实现检测请求合并、去重或排队。

---

## 9. 节点健康检测

### 9.1 检测流程

**REQ-HEALTH-001** 所有 Node 使用相同的健康检测流程。每次 Node 检测依次执行：

```text
TCP 检测
    ↓
URL 检测
    ↓
更新 Node 健康状态
```

无论 TCP 检测成功还是失败，都继续执行 URL 检测。TCP 和 URL 检测分别使用 Settings 中配置的超时时间。

### 9.2 TCP 检测

**REQ-HEALTH-002** TCP 检测用于检查 Node 服务器的基础 TCP 连接情况，其结果只用于页面展示、日志和人工排错，不参与 Node 最终健康判断，也不参与 AUTO 控制。Hysteria2 与其他 Node 使用相同流程，不增加协议专用分支；Hysteria2 的 TCP 检测允许失败，失败后仍继续执行 URL 检测。

- 检测成功：`tcp delay` 记录实际毫秒数；
- 检测超时：`tcp delay = -1`；
- 其他无法取得有效 delay 的失败：`tcp delay = null`。

### 9.3 URL 检测

**REQ-HEALTH-003** URL 检测必须通过被检测 Node 的真实代理流量完成。系统使用 sing-box Clash API delay 接口访问 Settings 中统一配置的 HTTPS 测试 URL。

Clash API 返回 HTTP 2xx 且 `delay > 0` 时检测成功：

```text
result = available
url delay = API 返回的 delay
```

其他情况均为检测失败：

```text
result = unavailable
```

- URL 检测超时：`url delay = -1`；
- 其他没有取得有效 delay 的失败：`url delay = null`。

Node 的最终健康状态只由 URL 检测结果决定。

### 9.4 Node 健康状态

**REQ-HEALTH-004** 每个 Node 在内存中保存最近一次完成检测的 `result`、`tcp delay`、`url delay`、`last checked time` 和 `failure reason`。

`result` 只有 `unknown`、`available` 和 `unavailable` 三种。Node 首次检测前：

```text
result = unknown
tcp delay = null
url delay = null
```

URL 检测成功时 `failure reason = null`；URL 检测失败时记录简单失败原因。

### 9.5 状态更新时间

**REQ-HEALTH-005** TCP 和 URL 检测全部完成后，一次性更新该 Node 的健康状态。检测过程中页面继续显示该 Node 上一次已经完成的检测结果。

健康状态只保存在内存中，不写入数据库。ProxyHub 重启以及 sing-box 启动或重启后，全部 Node 健康状态重新变为 `unknown`。

### 9.6 人工检测

**REQ-HEALTH-006** 用户可以从页面发起人工检测，每次选择以下一种检测范围：

- 任意一个现存的全局 Node，包括自建 Node 或 Subscription Node；
- 全部自建 Node；
- 某一个 Subscription 下的全部 Node；
- 全部全局 Node，包括自建 Node 和所有 Subscription Node。

人工检测遵循以下规则：

- 只允许在管理状态为 `running` 且 sing-box 实际进程正在运行时发起；
- 发起时确定本次 Node 集合，空集合直接返回没有可检测节点；
- 不持有运行控制锁，可以与 AUTO 控制、其他人工检测、Stop 或 Restart 并发；
- 检测过程中 sing-box 因 Stop、Restart 或意外退出而不可用时，尚未完成的检测允许失败；
- 检测完成时只更新仍然存在的 Node 健康展示状态和日志，Node 已不存在时丢弃其状态结果；
- 不修改 AUTO 的连续失败次数、Current Node、Fallback 或 Priority Recovery 状态，也不触发 AUTO 切换。

**REQ-HEALTH-007** AUTO 检测和人工检测都在每个 Node 的 TCP 和 URL 检测全部完成后更新其最近健康状态。同一 Node 存在并发检测时，按检测完成顺序更新，后完成的结果覆盖先完成的结果。AUTO 只使用其自身控制流程本次取得的检测结果作出判断，Node 最近健康状态只用于页面展示、日志和排错。

---

## 10. AUTO 故障切换

本章中的 AUTO 指 `type = auto` 的 Outbound。

每个 AUTO 包含一个 Fallback Node 和一个或多个 Candidate Node。Fallback Node 不参与 Candidate 自动择优；Candidate 直接使用完整 Node Pool 中的 priority，数值越小、优先级越高。

### 10.1 总体流程

```text
sing-box 启动或重启
        ↓
Current = Fallback，持续时间从零开始累计
        ↓
逐个处理 Routed AUTO
        ↓
Current == Fallback？
        ├── 是 → 扫描全部 Candidate
        │          ├── 成功切换 → Current = 最高 priority 的可用 Candidate
        │          └── 仍在 Fallback → 持续时间超时？
        │                                  ├── 否 → 处理下一个 AUTO
        │                                  └── 是 → 重启 sing-box，本周期结束
        │
        └── 否 → 检测 Current Candidate
                   ├── 连续失败达到阈值 → 成功切换 Fallback，本 AUTO 处理结束
                   └── 未达到阈值 → Priority Recovery 到期？
                                          ├── 否 → 处理下一个 AUTO
                                          └── 是 → 扫描更高 priority Candidate
                                                       ├── 有可用 → 切换
                                                       └── 无可用 → 保持 Current
```

核心原则：

```text
能切换就切换
无法恢复就待在 Fallback
Fallback 太久就重启 sing-box
sing-box 每次启动或重启成功后，所有运行状态全部重新开始
```

### 10.2 运行状态和初始化

**REQ-FAILOVER-001** AUTO 只在内存中保存 Current Node、当前 Candidate 连续失败次数、Fallback 持续时间和 Priority Recovery 计时，不建立额外状态机。

Current Node 为 Fallback 时累计实际经过的 Fallback 持续时间；不在 Fallback 时该时间为零。sing-box 每次启动或重启成功后，按 REQ-RUNTIME-003 清除上述状态，Routed AUTO 以 `Current Node = Fallback Node`、`failure count = 0`、`Fallback 持续时间 = 0` 重新开始。

### 10.3 每周期处理顺序

**REQ-FAILOVER-002** 后台控制循环逐个处理 Routed AUTO：

- Current Node 为 Fallback：执行 Fallback Recovery，然后判断 Fallback 持续时间是否超时；
- Current Node 为 Candidate：检测 Current Candidate，必要时切回 Fallback；未切回 Fallback 时，到期后执行 Priority Recovery。

未被 Route 引用的 AUTO 不执行检测或自动切换。

### 10.4 Current Candidate 检测和故障切换

**REQ-FAILOVER-003** Current Node 为 Candidate 时，每个控制周期检测一次 Current Candidate。只有本次检测的 URL 最终结果参与连续失败计数：

- 成功：`failure count = 0`；
- 失败：`failure count += 1`。

TCP 检测、人工检测、Fallback Recovery 和 Priority Recovery 的检测结果本身均不影响该计数。

**REQ-FAILOVER-004** 连续失败达到配置阈值时，立即通过 Clash API 切换到 Fallback。切换成功后：

```text
Current Node = Fallback Node
failure count = 0
Fallback 持续时间 = 0，并开始累计
```

该 AUTO 本周期处理结束，下一控制周期再执行 Fallback Recovery。

### 10.5 Fallback Recovery

**REQ-FAILOVER-005** AUTO 在周期开始处理时已经处于 Fallback，则扫描其全部 Candidate。Fallback Node 不参与扫描。

扫描完成后，只按 available 和 priority 选择：

- 存在 available Candidate：选择 priority 最高者并通过 Clash API 切换；
- 不存在 available Candidate：保持 Fallback。

不按 delay 排序，不要求连续成功，也不设置最短节点保持时间。

**REQ-FAILOVER-006** 从 Fallback 成功切换到 Candidate 后：

```text
Current Node = 选中的 Candidate
failure count = 0
Fallback 持续时间 = 0
Priority Recovery Interval 从切换成功时间重新计算
```

下一个控制周期开始检测新的 Current Candidate。

### 10.6 Candidate Priority Recovery

**REQ-FAILOVER-007** Current Node 为 Candidate、当前 Candidate 不是全部 Candidate 中 priority 最高者，并且达到 Priority Recovery Interval 时，执行 Priority Recovery。

只检测 priority 高于 Current Candidate 的 Candidate，不检测当前 Candidate、priority 更低的 Candidate 或 Fallback Node。当前 Candidate 已经是最高 priority Candidate 时不执行。

**REQ-FAILOVER-008** Priority Recovery 完成后：

- 存在 available 的更高 priority Candidate：选择 priority 最高者并切换；
- 不存在：保持 Current Candidate。

检测本身不影响连续失败次数。成功切换后将连续失败次数清零，并从切换成功时间重新计算 Priority Recovery Interval；没有成功切换时，从本次扫描完成时间重新计算该 Interval。

### 10.7 Fallback 超时重启

**REQ-FAILOVER-009** 每个周期先执行 Fallback Recovery。完成后仍在 Fallback，并且：

```text
Fallback 持续时间 >= Fallback Restart Timeout
```

则按 REQ-FAILOVER-010 主动重启 sing-box。不额外判断 Fallback 或其他 Node 的健康状态及既往重启次数。

**REQ-FAILOVER-010** Fallback 超时后按 Restart 的 Stop + Start 流程从最新数据库重新生成、检查并启动 sing-box：

后台恢复重启复用与用户发起的 Restart 相同的 Stop + Start 进程操作流程，但不改变管理层的运行意图；失败时管理状态仍为 `running`。

```text
重启成功
    ↓
按 REQ-RUNTIME-003 清空全部运行时状态
    ↓
所有 Routed AUTO 回到 Fallback，持续时间从零开始
    ↓
本控制周期结束
```

配置检查或启动失败时按 REQ-RUNTIME-005 记录错误，保持管理状态 `running`，下一控制周期由进程守护再次尝试恢复。Candidate 长时间无法恢复时，每次重新累计完整超时时间后可以再次重启。

第一版不设置重启次数上限、指数退避、cooldown、历史统计或其他恢复条件。

### 10.8 切换失败

**REQ-FAILOVER-011** 只有 Clash API 明确返回成功后，才修改 Current Node 和相关状态。切换失败时：

- Current Candidate → Fallback：记录错误并按 Restart 的 Stop + Start 流程从最新数据库重新生成、检查并启动 sing-box；成功后重置全部状态，失败后保持管理状态 `running` 并由下一周期的进程守护再次尝试；
- Fallback → Candidate：保持 Fallback 并继续累计持续时间，然后执行本周期的超时判断；
- Priority Recovery：保持 Current Candidate 和连续失败次数，从本次扫描完成时间重新计算 Priority Recovery Interval。

---

## 11. 管理页面与认证

### 11.1 页面范围

**REQ-UI-001** 桌面页面提供 Subscription、Node、Inbound、Outbound、Route、Settings、状态、关键日志和 sing-box 管理功能。Outbound 页面和 Route 目标选择中统一展示 DIRECT、MANUAL 和 AUTO：DIRECT 为只读系统项；用户创建的 Outbound type 只能是 `manual` 或 `auto`，仅允许按 REQ-OUTBOUND-006 在二者之间修改 type。DIRECT 不显示 Node、Current Node 或健康状态。

**REQ-UI-002** 桌面页面支持新增、修改、删除 Subscription、同步订阅节点、刷新订阅信息、对单个 Node 发起人工检测、按全部自建 Node、指定 Subscription 或全部全局 Node 发起人工批量检测、切换 MANUAL 的 Current Node、调整 MANUAL/AUTO 的 Node priority、Start、Stop、Restart、下载日志以及人工检查和升级 sing-box。Subscription 相关操作的运行状态限制遵循 REQ-CONFIG-001，删除和同步订阅节点产生的差异预览、级联影响与事务规则遵循第 6 章。

**REQ-UI-003** 移动页面只提供整体管理状态和实际进程状态、MANUAL/AUTO 状态、Node 健康状态、只读 DIRECT 状态项和 MANUAL 的 Current Node 切换，不提供结构配置、priority 编辑、Settings、升级或完整日志管理。

### 11.2 登录

**REQ-AUTH-001** 登录使用用户名和密码。默认用户名为 `admin`，默认密码为空；密码为空时按个人部署需求跳过认证。

**REQ-AUTH-002** 密码非空时，桌面页面、移动页面、全部内部 API 和日志下载都必须认证。系统提供登录和退出。

**REQ-AUTH-003** 密码只保存安全哈希，不保存或记录明文。修改用户名或密码后立即使既有会话失效并要求重新登录。

---

## 12. Settings、日志和默认值

### 12.1 Settings 行为

**REQ-SETTINGS-001** 所有应用设置使用单一 `data/settings.json` 文件持久化，并按运行调度、健康检测、AUTO 故障切换、Web 和认证等领域分组。Settings 不建立数据库表，也不使用数据库键值记录。

**REQ-SETTINGS-002** 各配置项是否允许通过 Settings 页面在线修改及其生效方式由 12.2 规定。不能在线修改的配置项只能直接修改 JSON，并在 ProxyHub 重启后生效。

**REQ-SETTINGS-003** ProxyHub 启动时加载 `data/settings.json`。文件不存在时，使用内置默认值创建完整文件。Settings 页面保存时必须先通过完整校验，再通过同目录临时文件原子替换正式文件，并同步更新当前进程的内存设置；非法值不得应用。

**REQ-SETTINGS-004** 通过 Settings 页面保存在线设置不取得运行控制锁，也不启动或重启 sing-box。保存不改变 MANUAL/AUTO 的 Current Node，不清空 Node 最近检测信息、AUTO 连续失败次数、Fallback 持续时间或 Priority Recovery 计时，也不主动检测或切换 Node。新设置用于保存后的后续相关处理；已经开始的任务不要求取消、重启或重新计算。Username 和 Password 保存后立即生效。

**REQ-SETTINGS-005** 用户直接编辑 `data/settings.json` 时，修改只在下次 ProxyHub 启动后生效。第一版不监视文件变化，也不为手工编辑提供运行时热加载。

**REQ-SETTINGS-006** `data/settings.json` 能够读取并解析为合法 JSON 对象但缺少部分已定义字段时，使用对应内置默认值在内存中补全，再执行完整校验；不得因为启动加载补全字段而自动重写原文件，用户后续通过 Settings 页面成功保存时再按 REQ-SETTINGS-003 写入完整设置。

`data/settings.json` 无法读取、不是合法 JSON、包含未知结构，或补全缺失字段后仍无法通过完整校验时，记录明确错误并终止 ProxyHub 启动，ProxyHub Web 和 sing-box 均不启动。文件中已经提供但值非法的字段不得用默认值静默替代；保留原文件，不自动修改、覆盖或静默回退，也不启动临时 Web 地址或修复页面。错误通过启动输出和正常日志渠道报告，不要求通过管理页面显示。

**REQ-SETTINGS-007** JSON 中只保存密码安全哈希，不保存明文密码。用于签名登录会话的随机 secret 不属于普通 Settings，应保存在独立密钥文件中，不在 Settings 页面显示。

**REQ-SETTINGS-008** 需求只规定 Settings 保存和启动加载前必须通过完整校验、非法值不得应用；端口、正整数、超时和取值范围等常规校验规则由实现设计确定，不在需求中逐项展开。

### 12.2 Settings 配置项与默认值

“在线修改”表示可以通过 Settings 页面修改且不需要重启 ProxyHub，具体生效方式遵循 REQ-SETTINGS-004。不能在线修改的设置只能直接修改 JSON，并在 ProxyHub 重启后生效。

| Setting | 默认值 | 在线修改 | 备注 |
|---|---:|:---:|---|
| Control Interval | 15 秒 | 是 | 一个控制周期完成后，到下一周期开始前的等待时间 |
| TCP Timeout | 3 秒 | 是 | 单个 Node 的 TCP 检测超时时间 |
| URL Timeout | 5 秒 | 是 | 单个 Node 的 URL 检测超时时间 |
| Test URL | `https://www.gstatic.com/generate_204` | 是 | 所有 Node 共用的 URL 健康检测地址 |
| Max Concurrency | 10 | 是 | 每个 AUTO 检测过程或每个人工检测请求内同时检测的最大 Node 数量 |
| Failure Threshold | 3 次 | 是 | Current Candidate 连续 URL 检测失败达到该次数后切换到 Fallback |
| Priority Recovery Interval | 60 秒 | 是 | Current Candidate 不是最高优先级时，扫描更高优先级 Candidate 的间隔 |
| Fallback Restart Timeout | 300 秒 | 是 | AUTO 持续处于 Fallback 达到该时间后重启 sing-box |
| Web Listen Address | `127.0.0.1` | 否 | ProxyHub Web 的监听地址 |
| Web Port | 8080 | 否 | ProxyHub Web 的监听端口 |
| Username | `admin` | 是 | 登录用户名 |
| Password | 空 | 是 | 为空时跳过认证；JSON 只保存密码哈希 |

### 12.3 日志

**REQ-LOG-001** 后端文件日志记录足够的运行和排错信息。桌面页面只显示最近关键事件，不提供完整日志浏览，但允许下载日志文件。Node 健康检测相关展示和日志必须明确区分 tcp delay 与 url delay，不使用未注明类型的单一 delay 表述。

**REQ-LOG-002** Node 切换、Fallback 持续超时、人工检测、sing-box 启动/停止/重启、配置生成和升级属于关键事件。

**REQ-LOG-003** 第一版不实现消息推送。未来推送可以作为关键事件日志的附加处理，但不得预先引入推送平台抽象。

---

## 13. sing-box 下载、升级与部署

### 13.1 下载与升级

**REQ-UPGRADE-001** ProxyHub Web 在 sing-box 不存在时仍可运行，状态显示“未安装”并且管理状态保持 stopped。用户可以人工下载官方 GitHub Release 中适用于 `amd64` 的 sing-box。下载与升级流程只匹配和安装 `amd64` 资产，不支持 32 位 x86、arm64 或其他架构。

**REQ-UPGRADE-002** sing-box 二进制存在时，页面始终显示检测到的本地当前版本；二进制不存在时显示“未安装”。管理状态为 stopped 或二进制不存在时，允许检查远程新版本并根据当前安装状态执行下载、安装或升级；管理状态为 running 时禁止检查远程新版本、下载和升级，只显示本地当前版本。下载、安装或升级替换使用运行控制锁，成功后保持 stopped，不自动启动 sing-box。

**REQ-UPGRADE-003** 下载、安装或升级采用最小失败保护：

1. 下载到同一文件系统的临时文件；

2. 验证下载完成、架构为 `amd64`、可执行并能读取合法版本；

3. 验证成功后原子替换正式二进制；

4. 任一步失败都保留原二进制、记录错误日志，并在发起操作的页面显示简单失败提示。

第一版不保存多版本、不自动回滚历史版本，也不后台自动升级。

### 13.2 部署

**REQ-DEPLOY-001** 第一版同时提供 Docker Compose 和 Ubuntu Python/venv 部署方式，共用同一种简单配置格式。

**REQ-DEPLOY-002** 支持 Ubuntu 20.04 及以上版本、`amd64` CPU；不要求支持 Windows、macOS、其他 Linux 发行版、32 位 x86 或 arm64。

---

## 14. 最低可靠性要求

**REQ-REL-001** 结构配置写操作、配置生成、sing-box 启停、MANUAL Current Node 人工切换和 sing-box 升级替换按 REQ-RUNTIME-007 使用同一把进程内运行控制锁串行执行。刷新订阅信息、Settings 保存和人工检测不使用该锁。第一版不建立跨进程锁或分布式事务。

**REQ-REL-002** 同步订阅节点的请求、解析或预览失败时原数据不变；用户确认后，Subscription（适用时）、Node、Current/Fallback 自动替换、MANUAL/AUTO 更新或删除和 Route 删除作为一个业务事务完成。

**REQ-REL-003** 删除 Subscription、Node、Inbound、MANUAL、AUTO 或 Route 前显示简单确认；涉及级联时显示受影响对象和 Current/Fallback 自动替换。删除 MANUAL/AUTO 时必须删除引用它的 Route，不得把 Route 自动或静默改为系统内置 DIRECT。

**REQ-REL-004** ProxyHub Web 已启动时，sing-box 启动或配置检查失败由前端显示简单错误和关键事件，详细信息写入可下载日志。Settings 文件异常导致 ProxyHub 无法启动时按 REQ-SETTINGS-006 通过启动输出和正常日志渠道报告。不建立大型结构化错误模型或专项错误页面。

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

- 自动同步订阅节点；

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

- [ ] Subscription 新增、修改、删除、同步订阅节点和刷新订阅信息在 running/stopped 状态下的限制一致，跳过、差异确认及事务边界得到确认；

- [ ] Outbound 的 `direct` / `manual` / `auto` 三种 type、DIRECT 不持久化、MANUAL/AUTO 至少两个 Node、统一 1 至 N priority，以及新建时由 `priority = 1` 的 Node 自动成为 MANUAL 的 Current Node 或 AUTO 的 Fallback Node 等行为得到确认；

- [ ] 无 Route、目标为 DIRECT 的 Route、目标为 MANUAL/AUTO 的 Route 三种场景语义明确；DIRECT 为前后端可见、只读、全局唯一且不持久化的系统对象，删除 MANUAL/AUTO 不会把 Route 静默改为 DIRECT；

- [ ] Node 删除、Subscription 删除和同步订阅节点导致的 Current/Fallback 自动替换、MANUAL/AUTO 删除和 Route 删除级联行为得到确认；

- [ ] AUTO 正常、故障、Fallback Recovery、Candidate Priority Recovery 和 Fallback 超时重启流程得到确认，Fallback 不参与 Candidate 择优且 Candidate 直接使用完整 Node Pool priority；

- [ ] 所有 Node 统一执行 TCP + URL 检测，TCP 不阻断 URL，最终健康结果仅由 URL 决定；tcp delay、url delay、超时记为 `-1` 和健康状态更新规则得到确认；

- [ ] 单 Node 检测及三种批量检测范围、并发规则及其与 AUTO 控制状态相互独立的行为得到确认；

- [ ] 管理状态与实际进程状态的区分、Start 成功后才进入 running、Restart 严格执行 Stop + Start、守护恢复始终使用最新数据库及单一运行控制锁的行为得到确认；

- [ ] 首次启动、仅有目标为 DIRECT 的 Route 时启动，以及只为被 Route 引用的 MANUAL/AUTO 生成运行时配置并按 Current/Fallback 规则初始化的行为得到确认；

- [ ] 页面、认证、Settings、日志和 sing-box `amd64` 下载/升级边界得到确认；

- [ ] Settings JSON 缺失字段补全与非法文件/非法值失败处理得到确认；

- [ ] 至少完成本文第 3 节场景以及无 Route、目标为 DIRECT 的 Route、目标为 MANUAL/AUTO 的 Route、type 修改、最少两个 Node、priority 和级联删除的验收描述；

- [ ] 后续数据模型和状态机设计不需要自行补充新的业务规则。

全部通过后，将本文标记为 `Requirements v1.0`，再进入数据模型和运行时状态机设计。
