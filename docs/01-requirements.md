# ProxyHub 个人版第一版需求规范

> 文档版本：v0.2（评审修订稿）

> 文档状态：待评审

> 更新日期：2026-08-28

> 适用范围：ProxyHub 新版本第一版

## 0. 文档说明

本文描述 ProxyHub 第一版“应该做什么”，是后续数据模型、状态机、sing-box 集成、页面、API 和验收设计的需求基准。

### 0.1 v0.2 变更说明

v0.2 基于 v0.1 评审结论统一修订正式需求，主要变更如下：

- 在第一版原则中补充“单一可信用户、正常操作路径、必要基本防护、避免过度设计”的实施边界；

- 补全 sing-box running 时 Subscription 新增、修改、删除和刷新的限制，并统一结构修改与运行期允许操作的口径；

- 重构 Outbound 业务模型：Outbound 统一分为 `direct` / `manual` / `auto` 三种 type；正文分别以 DIRECT、MANUAL 和 AUTO 指代三种类型的 Outbound；DIRECT 为系统内置且不持久化，MANUAL/AUTO 为用户创建并保存于数据库的 Node 出站，二者共用连续唯一的 Node priority；

- 将 DIRECT 明确为系统内置、全局唯一、只读且不持久化的系统对象，Route 必须显式选择 DIRECT、MANUAL 或 AUTO，并区分“没有 Route”和“Route 选择 DIRECT”；

- 统一所有 Node 的 TCP + URL 健康检测流程；TCP 结果只用于排错，最终健康结果只由 URL 检测决定，并将运行时状态拆分为 `tcp delay` 与 `url delay`；

- 精简认证要求，删除 v0.1 中对 CSRF、Cookie 属性和公网 TLS 终止方式的专项需求；

- 明确 `data/settings.json` 的错误处理：缺失字段可用内置默认值补全，非法 JSON、未知结构或非法值不得静默回退；

- sing-box 下载、升级和部署架构统一为 `amd64`，并明确 running/stopped/未安装状态下的版本展示和升级限制；

- 同步修订生命周期、配置生成、故障切换、页面、可靠性和冻结检查清单，使上述口径在全文保持一致。

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

- **Node Pool**：一个 MANUAL 或 AUTO 包含的 Node 集合；每个 Node 在该 Pool 中具有连续、唯一的 priority。

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

→ sing-box 未安装或没有任何有效 Route，保持 stopped

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

### 3.5 订阅刷新

```text

sing-box stopped

→ 用户请求刷新

→ 请求、解析、过滤和校验

→ 跳过无效或不支持的节点

→ 至少存在一个有效节点时生成差异预览

→ 同时展示节点变化、Current/Fallback 自动替换和级联删除影响

→ 用户确认：原子更新数据

→ 用户取消：不修改任何数据

```

Subscription 新增、修改、删除和刷新在 running 时均禁止，统一遵循 REQ-CONFIG-001。

### 3.6 人工修改配置

```text

用户停止 sing-box

→ 新增、修改、删除或刷新 Subscription，或修改 Node、Inbound、MANUAL/AUTO 的结构、type、Node Pool、Fallback/Current 角色或 Route

→ 用户再次点击 Start

→ 重新生成并检查完整配置

→ 成功后启动

```

MANUAL/AUTO 的 Node priority 调整属于 REQ-CONFIG-002 明确允许的运行期操作，不需要为此执行 Stop/Start。

### 3.7 sing-box 意外退出

```text

期望状态为 running

→ 控制循环发现 sing-box 已退出

→ 使用当前正式配置重新启动

→ 清空运行时健康及切换状态

→ 已生效的 MANUAL 恢复持久化的 Current Node

→ AUTO 从 Fallback Node 重新初始化

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

Subscription 新增、修改、删除和刷新的运行状态限制统一由 REQ-CONFIG-001 规定，本章不重复定义。

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

**REQ-SUB-009** 差异预览必须同时显示 Node 删除引起的 MANUAL 的 Current Node 或 AUTO 的 Fallback Node 自动替换、被删除的 MANUAL/AUTO 和被删除的 Route。用户确认后在一个业务事务中完成 Node、Outbound 和 Route 更新；用户取消时任何数据都不改变。

**REQ-SUB-010** 被跳过的节点不进入新订阅结果。因此它可能使原有同名 Node 出现在删除预览中；最终是否导入及执行自动替换、级联删除由用户查看完整预览后确认。

**REQ-SUB-011** 订阅 Node 为只读，不能人工修改协议参数；其内容只能由订阅刷新更新。自建 Node 与订阅 Node 在页面中必须显示不同来源。

**REQ-SUB-012** 明确删除订阅时，先展示其全部 Node 及 Current/Fallback 自动替换、MANUAL/AUTO 删除和 Route 删除等完整级联影响，用户确认后使用与刷新删除相同的规则和事务边界处理。

---

## 6. Inbound、Outbound 与 Route

### 6.1 Inbound

**REQ-INBOUND-001** 系统允许创建任意数量的 Inbound，支持 HTTP、SOCKS、Mixed、Shadowsocks 和 VMess。

**REQ-INBOUND-002** 每个 Inbound 独立定义名称、监听协议、监听地址、监听端口和该协议所需的认证参数。Mixed 在同一端口兼容 HTTP 和 SOCKS。

### 6.2 Outbound 通用约束

**REQ-OUTBOUND-001** 每个 MANUAL/AUTO 独立定义名称，由用户创建并保存于数据库，其 Node Pool 由全局 Node 组成。

**REQ-OUTBOUND-002** 每个 MANUAL 和 AUTO 必须始终至少包含两个不同 Node。Node 是全局对象，可以被多个 MANUAL/AUTO 复用，但在同一个 Node Pool 中只能出现一次。用户正常创建或编辑 Node Pool 时，少于两个 Node 不允许保存；全局 Node 删除、Subscription 删除或订阅刷新造成不足两个 Node 时，按 REQ-ROUTE-006 和 REQ-ROUTE-007 执行预览及级联删除。

**REQ-OUTBOUND-003** MANUAL/AUTO 的 Node Pool 中，每个 Node 都必须具有连续、唯一的 1 至 N priority，数值越小、优先级越高。页面按 priority 数值升序显示，`priority = 1` 的 Node 显示在最前；priority 的运行用途由 Outbound type 决定。

**REQ-OUTBOUND-004** 新建 MANUAL/AUTO 时，前端必须提交确定的 Node 顺序：逐个选择 Node 时按选择先后排序；一次同时选择多个 Node 时按 Node name 排序，name 相同时按 Node 的稳定标识排序。后端按前端提交顺序生成 priority。后续调整顺序时，保存后重新整理为连续、唯一的 1 至 N priority；修改 priority 不改变 MANUAL 的 Current Node 或 AUTO 的 Fallback Node。

**REQ-OUTBOUND-005** MANUAL 的 Current Node 和 AUTO 的 Fallback Node 必须属于各自 Node Pool。正常编辑 Node Pool 时，如果移除 MANUAL 的 Current Node 或 AUTO 的 Fallback Node，但仍保留至少两个 Node，则以保存后 priority 最高的 Node 自动替代。Current Node 发生运行时切换时，必须中断仍绑定旧节点的已有入站连接，使后续重连使用新的 Current Node；具体 sing-box 配置映射由模块设计规定。

### 6.3 MANUAL/AUTO

**REQ-OUTBOUND-006** 用户新建的 Outbound type 只能是 `manual` 或 `auto`，默认为 `manual`。只有 sing-box stopped 时才能在 MANUAL 与 AUTO 之间修改 type；修改 type 只改变运行策略，不增加、删除或重新排序 Node。DIRECT 不可转换为 MANUAL/AUTO，MANUAL/AUTO 也不可转换为 DIRECT。

**REQ-OUTBOUND-007** MANUAL 不执行自动故障切换。priority 只用于页面展示和配置中的 Node 顺序；新建 MANUAL 时不要求用户指定 Current Node，保存后 `priority = 1` 的 Node 自动成为初始持久化 Current Node。MANUAL 被 Route 引用并已写入当前 sing-box 配置时，用户可以在 running 状态人工切换 Current Node，只有 Clash API 明确确认成功后才持久化新选择；切换失败时保留原选择并在页面提示失败。人工切换不改变 priority。

**REQ-OUTBOUND-008** 新建 AUTO 时不要求用户指定 Fallback Node，保存后 `priority = 1` 的 Node 自动成为 Fallback Node；用户后续可以在 sing-box stopped 时手动修改。除 Fallback Node 外的其他 Node 全部是 Candidate Node。Fallback Node 的 priority 只用于页面展示和配置顺序，不参与 Candidate 自动择优；Candidate 按 priority 执行自动选择和 Candidate Priority Recovery。

**REQ-OUTBOUND-009** AUTO 的运行时 Current Node 完全由后台控制循环管理，不持久化，用户不能临时人工切换或锁定。只有被 Route 引用的 AUTO 才执行 AUTO 控制；每次 sing-box 实际启动或重启成功后，其 Current Node 从 Fallback Node 初始化。

**REQ-OUTBOUND-010** 将 type 从 `manual` 改为 `auto` 时，原持久化 Current Node 直接作为 Fallback Node；将 type 从 `auto` 改为 `manual` 时，原 Fallback Node 直接作为持久化 Current Node，修改前 AUTO 的运行时 Current Node 不保留。修改 type 时保留原 Node Pool 和全部 priority，不要求用户重新选择 Node 或排序，并清除该 MANUAL/AUTO 的临时控制状态。

### 6.4 Route

**REQ-ROUTE-001** Route 只表达一个 Inbound 的流量目标，不提供规则分流或额外“服务”业务层。每条 Route 必须引用一个 Inbound 和一个 Outbound；目标 Outbound 可以是系统内置 DIRECT，也可以是数据库中现存的 MANUAL 或 AUTO。不得以目标缺失、空引用或无效引用表示 DIRECT。

**REQ-ROUTE-002** 一个 Inbound 最多被一条 Route 引用；一个 Outbound 可以被零条、一条或多条 Route 引用。多条 Route 引用同一个 MANUAL/AUTO 时，共享其 Node Pool、Current Node 和运行状态；任意数量的 Route 可以选择系统内置 DIRECT。

**REQ-ROUTE-003** 前端和内部 API 使用稳定的系统标识表示 DIRECT；创建或修改 Route 时，该标识可以作为合法的 Outbound 引用。

**REQ-ROUTE-004** 未被 Route 引用的 Inbound 和 MANUAL/AUTO 只保存于数据库，不生成其对应的 Inbound 或 MANUAL/AUTO 运行时配置；被 Route 引用的对象才生成对应配置。Route 选择 DIRECT 时，相关 Inbound 和系统内置 DIRECT 正常写入配置并对外监听，流量直接访问目标地址。DIRECT 的具体 sing-box 配置映射由模块设计规定。

**REQ-ROUTE-005** 删除 Inbound、MANUAL 或 AUTO 时，一并删除引用它的 Route。删除 MANUAL/AUTO 不得把原 Route 自动或静默改为 DIRECT；DIRECT 不可删除。

**REQ-ROUTE-006** 删除一个或多个 Node 时，以本次操作全部 Node 删除完成后的剩余 Node Pool 为准，对所有受影响的 MANUAL/AUTO 按以下规则处理：

- MANUAL/AUTO 剩余至少两个 Node：保留其余 Node 的相对顺序，重新整理为连续、唯一的 1 至 N priority；

- MANUAL 的持久化 Current Node 被删除时，以剩余 Node 中 priority 最高者作为新的持久化 Current Node；

- AUTO 的 Fallback Node 被删除时，以剩余 Node 中 priority 最高者作为新的 Fallback Node；

- MANUAL/AUTO 剩余不足两个 Node：删除该 MANUAL/AUTO，并继续删除引用它的全部 Route。

**REQ-ROUTE-007** 人工删除一个或多个 Node、删除 Subscription，以及订阅刷新删除 Node，都使用相同的级联规则。执行前必须向用户展示完整影响，包括 Current/Fallback Node 的自动替换、MANUAL/AUTO 删除和 Route 删除；用户确认后，在同一个业务事务中完成 Subscription（适用时）、Node、Outbound 和 Route 的全部变更。

**REQ-ROUTE-008** 正常编辑 MANUAL/AUTO 的 Node Pool 时，用户必须保持至少两个 Node；如果移除 Current/Fallback Node 但仍满足最少节点数，则按 REQ-OUTBOUND-005 自动替换。由全局 Node 删除、Subscription 删除或订阅刷新造成的 Node Pool 缩减不按普通编辑拒绝保存，而按 REQ-ROUTE-006 和 REQ-ROUTE-007 执行预览、替换和级联删除。

---

## 7. 配置编辑与 sing-box 配置生命周期

### 7.1 运行期间允许的修改

**REQ-CONFIG-001** sing-box running 时，禁止新增、修改、删除或刷新 Subscription，禁止新增、修改或删除 Node、Inbound 和 Route，禁止新增或删除 MANUAL/AUTO，以及修改 MANUAL/AUTO 的名称、type、Node Pool、AUTO 的 Fallback Node 或通过结构编辑修改 MANUAL 的 Current Node 等会改变配置结构或持久化选择语义的内容。REQ-CONFIG-002 明确允许的 MANUAL Current Node 人工切换和 MANUAL/AUTO 的 Node priority 调整不属于此处禁止的 Outbound 结构修改。DIRECT 始终只读，不受运行状态影响。

**REQ-CONFIG-002** running 时允许：查看状态、人工检测 Node、人工切换 MANUAL 的 Current Node、调整 MANUAL/AUTO 的 Node priority、修改不改变 sing-box 结构的 Settings，以及停止或重启 sing-box。

**REQ-CONFIG-003** MANUAL/AUTO 的 Node priority 在 running 时保存后均不得因保存操作立即检测、择优或切换 Current Node。MANUAL 的新 priority 只影响页面顺序及下次生成的完整配置；AUTO 的新 priority 在后续 Fallback Recovery 或 Candidate Priority Recovery 选择 Candidate 时生效。

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

- 所有合法的全局 Node 独立出站，包括未被任何 MANUAL/AUTO 引用的 Node；

- 被至少一条 Route 引用的 MANUAL/AUTO；

- Route 使用的系统内置 DIRECT；

- 仅被 Route 引用的 Inbound；

- 现存 Route 映射；

- 仅监听本机的 Clash API。

MANUAL/AUTO、DIRECT、Node 和 Route 到 sing-box 配置对象、tag 及字段的具体映射由 sing-box 模块设计规定。实现必须满足本文关于 Node Pool priority、MANUAL 的 Current Node、AUTO 的 Fallback Node、启动初始化、连接中断和 DIRECT Route 的业务要求，不得由历史运行状态覆盖 MANUAL/AUTO 的初始化选择。

**REQ-CONFIG-006** 系统保留上一份可用正式配置供人工排错，但新配置检查失败后不自动恢复或启动旧配置。

**REQ-CONFIG-007** 对会写入配置的 Inbound 执行基本监听地址和端口冲突校验，包括 Inbound 之间以及与 ProxyHub Web、Clash API 的明显冲突。不执行通用操作系统端口扫描。

---

## 8. ProxyHub 运行任务

### 8.1 启动任务

**REQ-RUNTIME-001** ProxyHub 在内存中维护 sing-box 的期望状态。人工 Start 和 Restart 按 REQ-CONFIG-004 生成、检查配置并在成功后进入 running；人工 Stop 或配置检查失败后进入 stopped。stopped 时不执行进程守护。手动 Stop 状态不跨 ProxyHub 重启持久化。

**REQ-RUNTIME-002** ProxyHub 启动时，只有同时满足以下条件才自动生成、检查并启动 sing-box：

- sing-box 二进制存在；

- Settings 已成功加载并通过校验；

- 数据库至少有一条能够生成有效配置的 Route，包括目标为系统内置 DIRECT 的 Route。

条件不满足或配置检查失败时，Web 正常运行并保持 sing-box stopped。没有 Route 与 Route 选择 DIRECT 的含义不同；只包含目标为 DIRECT 的 Route 的配置属于可启动的有效配置。

**REQ-RUNTIME-003** 每次 sing-box 实际启动或重启成功后，清空 Node 健康状态，以及 AUTO 的连续失败次数、相关计时和其他临时控制状态；被 Route 引用的 MANUAL 恢复持久化的 Current Node，Routed AUTO 从 Fallback Node 初始化并从启动成功时开始记录 Fallback 持续时间。不得在启动前检测 Candidate 或据此改变初始化选择。

### 8.2 后台控制任务

**REQ-RUNTIME-004** ProxyHub 只运行一个串行后台控制循环，每个周期严格按以下顺序执行：

1. sing-box 进程守护；

2. AUTO 故障检测与切换；

3. 全局 Node 扫描已启用且到期时，执行全局扫描。

期望状态为 running 而 sing-box 意外退出时，进程守护使用当前正式配置重启 sing-box；重启成功后按 REQ-RUNTIME-003 初始化并结束本周期。AUTO 任务只处理 Routed AUTO，具体规则由第 10 章规定；任何 AUTO 触发恢复性重启后同样结束本周期。全局 Node 扫描可以通过 Settings 开启或关闭，检测结果只用于更新 Node 健康状态、页面展示和日志，不参与 AUTO 调度，也不修改任何 AUTO 控制状态。

本周期全部处理完成后等待配置的基础间隔，再开始下一周期，不补跑错过的墙钟周期。不同控制周期不得重叠，检测批次之间也不得重叠；单个检测批次内部可以使用受限并发。第一版不建立多后台 worker、并行状态机、重启队列、指数退避或复杂冷却机制。

---

## 9. 节点健康检测

### 9.1 检测步骤

**REQ-HEALTH-001** 所有 Node 均可执行健康检测。每次检测先执行 TCP 检测，再执行 URL 检测，并分别记录 tcp delay 和 url delay；TCP 检测无论成功或失败都继续执行 URL 检测。

**REQ-HEALTH-002** Node 的最终健康结果只由 URL 检测结果决定：URL 检测成功时 `result = available`，失败时 `result = unavailable`。TCP 检测结果和 tcp delay 只供页面查看、日志记录与人工排错，不参与健康判定或 AUTO 控制。

**REQ-HEALTH-003** URL 检测必须通过被检测 Node 的真实代理流量，使用 sing-box Clash API delay 接口。API 返回 2xx 且 `delay > 0` 时 URL 检测成功，并记录该值为 url delay；其他结果均视为 URL 检测失败。

**REQ-HEALTH-004** 所有 Node 共用一个可配置 HTTPS 测试 URL。TCP 与 URL 检测使用不同的可配置超时。检测成功时，tcp delay 和 url delay 均以毫秒记录；超时和其他失败的取值遵循 REQ-HEALTH-005。

### 9.2 Node 健康状态

**REQ-HEALTH-005** 每个 Node 在内存中保存最近一次已完成检测的 `result`、`tcp delay`、`url delay`、`last checked time` 和 `failure reason`；`result` 只有 `unknown`、`available` 和 `unavailable` 三种。首次检测前 `result = unknown`，两个 delay 均为空；检测成功时对应 delay 记录实际毫秒数，检测超时时记录为 `-1`，其他未取得有效 delay 的情况为空。URL 检测成功时 `failure reason` 为空，失败时记录 URL 检测失败原因。

TCP 超时时继续执行 URL 检测；`tcp delay = -1` 不影响最终健康结果。`url delay = -1` 表示 URL 检测超时，此时 `result = unavailable`。

**REQ-HEALTH-006** TCP 和 URL 检测全部完成后，一次性更新 Node 健康状态；检测期间继续展示最近一次已完成的结果。健康状态不写入数据库，ProxyHub 或 sing-box 重启后重新检测。

**REQ-HEALTH-007** 人工检测可以更新 Node 健康状态，但不修改 AUTO 的连续失败次数、Current Node、Fallback 状态或其他自动控制状态。Node 健康状态与 AUTO 控制状态分别管理；AUTO 控制只采用对应控制步骤产生的检测结果。

### 9.3 检测入口与并发

**REQ-HEALTH-009** 页面人工检测只在 sing-box running 且当前没有检测批次时可用。stopped、未安装或已有批次运行时，页面不启动临时进程，分别提示不可检测或“检测进行中”。

**REQ-HEALTH-010** 同一时刻只运行一个检测批次；批次内部可以使用数量受限的并发。控制循环等待批次全部完成后再串行处理状态，不允许检测批次重叠。

---

## 10. AUTO 故障切换

本章中的 AUTO 均指 `type = auto` 的 Outbound。Fallback Node 虽具有完整 Node Pool 中的 priority，但始终排除在 Candidate 检测、自动择优和 Candidate Priority Recovery 之外；Candidate 之间直接比较其在完整 Node Pool 中的 priority，不单独重新编号。

### 10.1 AUTO 处理顺序与状态

**REQ-FAILOVER-001** 后台控制任务逐个处理 Routed AUTO。对每个 AUTO，Current Node 不是 Fallback Node 时，先执行当前 Candidate 检测和必要的故障切换，再执行到期的 Candidate Priority Recovery；周期开始处理时 Current Node 已是 Fallback Node 时，先执行 Fallback Recovery，再判断 Fallback 持续时间是否超时。

**REQ-FAILOVER-002** AUTO 的运行状态只保存在内存中，至少包括 Current Node、连续失败次数、Fallback 开始时间和上次 Priority Recovery Scan 时间；状态可以由 Current Node 是否为 Fallback 或其 Node Pool priority 推导，不引入额外复杂状态机。

### 10.2 当前 Candidate 健康检测与切换

**REQ-FAILOVER-003** 对每个 Current Node 不是 Fallback Node 的 Routed AUTO，每个控制周期检测 Current Node。只有这种当前 Candidate 自动检测的 URL 最终结果参与该 AUTO 的连续失败计数：失败加一，成功清零。TCP 结果、Fallback Recovery、Priority Recovery、全局扫描和人工检测均不得增加或清零该计数。

**REQ-FAILOVER-004** 当前 Candidate 连续失败达到阈值时：

1. 本周期通过 Clash API 立即切换到 Fallback Node；

2. 切换成功后将 Current Node 更新为 Fallback Node，清零连续失败次数，并从切换成功时开始记录 Fallback 持续时间；

3. 该 AUTO 本周期处理结束，不在同一周期执行 Fallback Recovery；

4. 同一周期有多个 AUTO 达到阈值时，控制循环仍按顺序逐个处理。

Current Node 切换后的已有连接中断行为由 REQ-OUTBOUND-005 规定，本章不重复定义配置实现。

### 10.3 从 Fallback Node 恢复

**REQ-FAILOVER-005** 周期开始处理时 Current Node 已经是 Fallback Node 的 Routed AUTO，每个周期检测该 AUTO 的全部 Candidate Node。Fallback Node 不作为 Candidate；它可以由全局扫描等检测记录健康状态，用于页面展示和人工排错。

**REQ-FAILOVER-006** Candidate 检测批次结束后：

- 存在 available Candidate：立即选择其中 Node Pool priority 最高者切换；

- 不按 tcp delay 或 url delay 排序；

- 不要求连续成功次数或最短保持时间；

- 没有 available Candidate Node：保持 Fallback Node。

成功切换到 Candidate 后清除 Fallback 持续时间，连续失败次数保持为零；不得切换到已知 unavailable Candidate。

### 10.4 Candidate Priority Recovery

**REQ-FAILOVER-007** Current Node 不是 Fallback Node、Current Candidate 不是全部 Candidate 中 Node Pool priority 最高者，并且距离上次 Priority Recovery Scan 已达到配置间隔时，只检测 priority 高于 Current Candidate 的全部 Candidate Node。Fallback Node 即使 priority 更高也不参与；不得检测当前 Candidate 或 priority 更低的 Candidate。

**REQ-FAILOVER-008** Priority Recovery Scan 结束后，存在 available 的更高 priority Candidate 时，立即选择其中 priority 最高者切换；否则保持当前 Candidate。该机制不按 tcp delay 或 url delay 排序，不要求连续成功多次，不设置最短节点保持时间，也不增加或清零当前 Candidate 故障检测使用的连续失败次数。Current Candidate 已是全部 Candidate 中最高 priority 时不执行 Priority Recovery Scan。

### 10.5 Fallback 持续超时后的恢复性重启

**REQ-FAILOVER-009** 每个处于 Fallback 的 Routed AUTO 必须先完成本周期 Fallback Recovery。完成后 Current Node 仍为 Fallback Node，且持续处于 Fallback 的时间达到配置的 Fallback Restart Timeout 时，使用当前正式配置重启整个 sing-box。触发条件不要求 Fallback Node unavailable，也不要求全部 Candidate 和 Fallback Node 均 unavailable；即使 Fallback available 而全部 Candidate unavailable，达到超时后也允许重启。

**REQ-FAILOVER-010** Fallback 持续超时重启是用于重新建立 DNS、连接和 sing-box 内部运行状态的主动恢复机制。重启成功后按 REQ-RUNTIME-003 重新初始化；如果 Candidate 长时间无法恢复，允许系统在每次重新累计完整 Fallback Restart Timeout 后再次重启。第一版不设置指数退避、重启次数上限、复杂 cooldown 或基于 Fallback 健康状态的附加条件。

**REQ-FAILOVER-011** Fallback Recovery 必须先于超时判断。若已达到超时但本周期发现 available Candidate 并成功切换，则清除 Fallback 持续时间，本周期不执行恢复性重启。保持 Fallback 时，不停止 Inbound、不修改 Route，也不切换到已知 unavailable Candidate；一次恢复性重启会清除其他 AUTO 的临时控制状态。

### 10.6 切换失败

**REQ-FAILOVER-012** 只有 Clash API 明确确认成功后才修改内存 Current Node 和相关状态。切换失败时：

- 故障 Candidate Node 切换到 Fallback Node 失败：记录关键事件并重启 sing-box；

- Fallback Node 恢复 Candidate Node 失败：保持 Fallback Node，下周期重新检测和尝试；

- Priority Recovery 切换到更高 priority Candidate 失败：保持当前 Candidate，后续到期时重新扫描和尝试；

- MANUAL 的人工切换失败：保持原选择并向页面返回失败；

- 如果 sing-box 已退出，由同一串行后台控制循环完成重启，不并发执行第二个恢复动作。

---

## 11. 管理页面与认证

### 11.1 页面范围

**REQ-UI-001** 桌面页面提供 Subscription、Node、Inbound、Outbound、Route、Settings、状态、关键日志和 sing-box 管理功能。Outbound 页面和 Route 目标选择中统一展示 DIRECT、MANUAL 和 AUTO：DIRECT 为只读系统项；用户创建的 Outbound type 只能是 `manual` 或 `auto`，仅允许按 REQ-OUTBOUND-006 在二者之间修改 type。DIRECT 不显示 Node、Current Node 或健康状态。

**REQ-UI-002** 桌面页面支持新增、修改、删除和刷新 Subscription、人工检测 Node、切换 MANUAL 的 Current Node、调整 MANUAL/AUTO 的 Node priority、Start、Stop、Restart、下载日志以及人工检查和升级 sing-box。Subscription 相关操作的运行状态限制遵循 REQ-CONFIG-001，删除和刷新产生的差异预览、级联影响与事务规则遵循第 5 章。

**REQ-UI-003** 移动页面只提供整体状态、MANUAL/AUTO 状态、Node 健康状态、只读 DIRECT 状态项和 MANUAL 的 Current Node 切换，不提供结构配置、priority 编辑、Settings、升级或完整日志管理。

### 11.2 登录

**REQ-AUTH-001** 登录使用用户名和密码。默认用户名为 `admin`，默认密码为空；密码为空时按个人部署需求跳过认证。

**REQ-AUTH-002** 密码非空时，桌面页面、移动页面、全部内部 API 和日志下载都必须认证。系统提供登录和退出。

**REQ-AUTH-003** 密码只保存安全哈希，不保存或记录明文。修改用户名或密码后立即使既有会话失效并要求重新登录。

---

## 12. Settings、日志和默认值

### 12.1 Settings 行为

**REQ-SETTINGS-001** 所有应用设置使用单一 `data/settings.json` 文件持久化，并按 Web、Clash API、健康检测和认证等领域分组。Settings 不建立数据库表，也不使用数据库键值记录。

**REQ-SETTINGS-002** Settings 页面允许修改检测、故障切换、登录用户名和密码设置。Web 和 Clash API 的监听地址、端口不在页面修改，只能直接修改 JSON 并重启 ProxyHub。

**REQ-SETTINGS-003** ProxyHub 启动时加载 `data/settings.json`。文件不存在时，使用内置默认值创建完整文件。Settings 页面保存时必须先校验完整设置，再通过同目录临时文件原子替换正式文件，并同步更新当前进程的内存设置。

**REQ-SETTINGS-004** 通过 Settings 页面保存检测或故障设置不重启 sing-box，也不改变 Current Node；系统清空健康结果、连续失败次数和相关检测与控制状态，使新参数从下一控制周期生效。登录用户名和密码保存后立即生效。

**REQ-SETTINGS-005** 用户直接编辑 `data/settings.json` 时，修改只在下次 ProxyHub 启动后生效。第一版不监视文件变化，也不为手工编辑提供运行时热加载。

**REQ-SETTINGS-006** `data/settings.json` 无法读取、不是合法 JSON、包含未知结构，或使用内置默认值补全后仍无法通过完整校验时，ProxyHub 不应用该文件，保留原文件并明确报告错误，且不得启动 sing-box。文件能够读取并解析为合法 JSON 对象但缺少部分已定义字段时，使用对应内置默认值在内存中补全，并在完整校验通过后加载；文件中已经提供但值非法的字段不得用默认值静默替代。启动加载时不得因为字段补全自动重写原文件，用户后续通过 Settings 页面成功保存时再按 REQ-SETTINGS-003 写入完整设置。

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

**REQ-LOG-001** 后端文件日志记录足够的运行和排错信息。桌面页面只显示最近关键事件，不提供完整日志浏览，但允许下载日志文件。Node 健康检测相关展示和日志必须明确区分 tcp delay 与 url delay，不使用未注明类型的单一 delay 表述。

**REQ-LOG-002** Node 切换、Fallback 持续超时、全局 Node 扫描、sing-box 启动/停止/重启、配置生成和升级属于关键事件。

**REQ-LOG-003** 第一版不实现消息推送。未来推送可以作为关键事件日志的附加处理，但不得预先引入推送平台抽象。

---

## 13. sing-box 下载、升级与部署

### 13.1 下载与升级

**REQ-UPGRADE-001** ProxyHub Web 在 sing-box 不存在时仍可运行，状态显示“未安装”并保持 stopped。用户可以人工下载官方 GitHub Release 中适用于 `amd64` 的 sing-box。下载与升级流程只匹配和安装 `amd64` 资产，不支持 32 位 x86、arm64 或其他架构。

**REQ-UPGRADE-002** sing-box 二进制存在时，页面始终显示检测到的本地当前版本；二进制不存在时显示“未安装”。sing-box stopped 或二进制不存在时，允许检查远程新版本并根据当前安装状态执行下载、安装或升级；running 时禁止检查远程新版本、下载和升级，只显示本地当前版本。成功下载、安装或升级后保持 stopped，不自动启动 sing-box。

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

**REQ-REL-001** Subscription 刷新、结构修改、配置生成、sing-box 启停和升级等改变状态的操作在单进程内串行执行。第一版不建立跨进程锁或分布式事务。

**REQ-REL-002** 订阅请求、解析或预览失败时原数据不变；用户确认导入后，Node 更新、Current/Fallback 自动替换、MANUAL/AUTO 更新或删除和 Route 删除作为一个业务事务完成。

**REQ-REL-003** 删除 Subscription、Node、Inbound、MANUAL、AUTO 或 Route 前显示简单确认；涉及级联时显示受影响对象和 Current/Fallback 自动替换。删除 MANUAL/AUTO 时必须删除引用它的 Route，不得把 Route 自动或静默改为系统内置 DIRECT。

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

- [ ] Subscription 新增、修改、删除、刷新在 running/stopped 状态下的限制一致，跳过、差异确认及事务边界得到确认；

- [ ] Outbound 的 `direct` / `manual` / `auto` 三种 type、DIRECT 不持久化、MANUAL/AUTO 至少两个 Node、统一 1 至 N priority，以及新建时由 `priority = 1` 的 Node 自动成为 MANUAL 的 Current Node 或 AUTO 的 Fallback Node 等行为得到确认；

- [ ] 无 Route、目标为 DIRECT 的 Route、目标为 MANUAL/AUTO 的 Route 三种场景语义明确；DIRECT 为前后端可见、只读、全局唯一且不持久化的系统对象，删除 MANUAL/AUTO 不会把 Route 静默改为 DIRECT；

- [ ] Node 删除、Subscription 删除和订阅刷新导致的 Current/Fallback 自动替换、MANUAL/AUTO 删除和 Route 删除级联行为得到确认；

- [ ] AUTO 正常、故障、Fallback Recovery、Candidate Priority Recovery 和 Fallback 超时重启流程得到确认，Fallback 不参与 Candidate 择优且 Candidate 直接使用完整 Node Pool priority；

- [ ] 所有 Node 统一执行 TCP + URL 检测，TCP 不阻断 URL，最终健康结果仅由 URL 决定；tcp delay、url delay、超时记为 `-1` 和健康状态更新规则得到确认；

- [ ] 人工检测、可关闭的全局扫描与 AUTO 控制状态相互独立，且进程守护、AUTO 故障切换、全局扫描的串行执行顺序得到确认；

- [ ] Start、Restart、守护重启、首次启动、仅有目标为 DIRECT 的 Route 时启动，以及只为被 Route 引用的 MANUAL/AUTO 生成运行时配置并按 Current/Fallback 规则初始化的行为得到确认；

- [ ] 页面、认证、Settings、日志和 sing-box `amd64` 下载/升级边界得到确认；

- [ ] Settings JSON 缺失字段补全与非法文件/非法值失败处理得到确认；

- [ ] 至少完成本文第 3 节场景以及无 Route、目标为 DIRECT 的 Route、目标为 MANUAL/AUTO 的 Route、type 修改、最少两个 Node、priority 和级联删除的验收描述；

- [ ] 后续数据模型和状态机设计不需要自行补充新的业务规则。

全部通过后，将本文标记为 `Requirements v1.0`，再进入数据模型和运行时状态机设计。
