# ProxyHub 个人版第一版需求规范

> 文档版本：v1.0

> 文档状态：前 9 章冻结

> 更新日期：2026-09-17

> 适用范围：ProxyHub 新版本第一版

---

## 0. 文档说明

本文描述 ProxyHub 第一版“应该做什么”，是后续数据模型、状态机、sing-box 集成、页面、API 和验收设计的需求基准。

---

## 1. 产品目标与实施边界

### 1.1 产品目标

**REQ-GEN-001** ProxyHub 是供单人使用、自行部署的本地代理网关管理工具。

**REQ-GEN-002** 系统接收机场订阅节点和用户自建节点，将远程节点组织为代理出口，并通过本地代理入站供本机或其他设备使用。

**REQ-GEN-003** 系统以 sing-box 作为唯一代理引擎，提供节点健康检测、自动故障恢复、手动节点切换及 sing-box 生命周期管理。

### 1.2 第一版原则

**REQ-GEN-004** 第一版服务个人家庭实际使用，不以公共服务、多用户平台、企业部署或通用代理管理平台为目标。

**REQ-GEN-005** 第一版优先保证主要行为简单、确定、可排错，不为低概率异常建立复杂恢复状态、分布式任务、历史任务或企业级高可靠机制。

**REQ-GEN-006** 第一版面向单一可信用户，仅实现当前需求必需的基本防护，不为异常场景和未来需求增加额外复杂设计。

**REQ-GEN-007** 系统只支持单 ProxyHub 实例、单 Web 进程、单 sing-box 进程和单后台控制循环。同一数据目录不得同时运行多个 ProxyHub 实例。

---

## 2. 业务模型与基本约束

### 2.1 核心关系

Subscription 和用户自建配置用于产生 Node。

Node 可以被 MANUAL/AUTO 使用；DIRECT 不包含 Node。一个 MANUAL/AUTO 可以包含多个 Node。

Inbound 表示本地代理入口，Outbound 表示流量出口。Outbound 分为 DIRECT、MANUAL 和 AUTO 三种类型。

用户分别选择一个 Inbound 和一个 Outbound，创建一条 Route，用于建立该 Inbound 到该 Outbound 的流量映射。

### 2.2 名词

- **Subscription**：用户保存的机场订阅及其 Filter/Exclude 设置。支持 **Sync** 和 **Refresh** 两个动作：Sync 用于新增、修改或删除 Subscription Node；Refresh 仅更新流量、到期时间等展示元信息，不修改 Node。
- **Node**：一个可生成 sing-box 远程出站的代理节点，来源为订阅或自建。
- **Inbound**：向本机或其他设备提供服务的本地监听入口。
- **Outbound**：所有流量出口的统称，`type` 只有 `direct`、`manual` 和 `auto` 三种。
- **DIRECT**：`type = direct` 的系统内置 Outbound，全局唯一、只读，不包含 Node 且不保存数据库记录，可被 Route 显式选择。
- **MANUAL/AUTO**：保存在数据库中的用户 Outbound，包含一个 Node Pool，并在 Pool 中指定一个 Default Node。
- **Node Pool**：MANUAL/AUTO 包含的有序 Node 集合。Pool 中 Node 的 `priority` 唯一且允许不连续，数值越小优先级越高。
- **Default Node**：MANUAL/AUTO 在 Node Pool 中持久化指定的默认 Node。MANUAL 使用 Default Node 初始化 Current Node；AUTO 的 Default Node 同时作为 Fallback Node。
- **MANUAL**：`type = manual` 的 Outbound。运行时 Current Node 由 Default Node 初始化，之后由用户手动切换，不执行自动故障切换。
- **AUTO**：`type = auto` 的 Outbound。Default Node 作为 Fallback Node，运行时 Current Node 由后台控制循环管理。
- **Candidate Node**：AUTO 的 Node Pool 中除 Default Node 外的 Node。Candidate Node 直接使用其在 Node Pool 中的 `priority` 参与自动择优和 Priority Recovery，不单独重新编号。
- **Fallback Node**：AUTO 的 Default Node。当自动切换无法选出可用 Candidate Node 时作为备用节点，不参与 Candidate 自动择优和 Priority Recovery。
- **Current Node**：MANUAL/AUTO 在当前 sing-box 运行周期中实际生效的 Node，仅保存在运行时内存中。MANUAL 由 Default Node 初始化并由用户管理；AUTO 由后台控制循环管理。
- **Runtime State**：ProxyHub 在当前 sing-box 运行周期中维护的临时运行状态，包括 Node 健康状态及检测信息、Current Node、AUTO 连续失败次数及相关计时。仅保存在内存中，不跨运行周期保留，不包括管理状态和实际进程状态。
- **Route**：一个 Inbound 到一个 Outbound 的明确流量映射；目标 Outbound 可以是 DIRECT、MANUAL 或 AUTO。
- **Routed AUTO**：至少被一条 Route 引用的 AUTO。该名称只表示 Route 引用关系，不表示 sing-box 当前一定处于 `running` 状态。
- **管理状态**：ProxyHub 维护的 sing-box 生命周期状态，只有 `running` 和 `stopped` 两种，与 sing-box 实际进程状态相互独立。

### 2.3 全局不变量

**REQ-MODEL-001** 每条 Route 必须引用一个 Inbound 和一个 Outbound。一个 Inbound 最多被一条 Route 引用；一个 Outbound 可以被多条 Route 引用。Outbound 可以是 DIRECT、MANUAL 或 AUTO。

**REQ-MODEL-002** 多条 Route 引用同一个 MANUAL/AUTO 时，共享其 Node Pool、priority、Default Node 以及 Current Node 等 Runtime State。DIRECT 不具有 Node Pool、Default Node 或 Current Node。

**REQ-MODEL-003** Node 是全局实体，可以被多个 MANUAL/AUTO 复用，但在同一个 Node Pool 中只能出现一次。每个 MANUAL/AUTO 必须至少包含两个不同 Node。

**REQ-MODEL-004** Subscription、Node、Inbound、MANUAL/AUTO、Route、Node Pool priority 和 Default Node 持久化在数据库中；Settings 通过独立配置文件持久化。DIRECT 不保存数据库记录；Current Node、Node 健康状态、delay 和失败计数等 Runtime State 只保存在内存中。

---

## 3. 核心使用场景

### 3.1 首次安装与配置

```text
启动 ProxyHub Web
→ sing-box 应用不存在或没有有效 Route，管理状态保持 stopped
→ 用户下载 sing-box
→ 添加 Subscription 或自建 Node
→ 创建 MANUAL/AUTO、Inbound 和 Route
→ 用户执行 Start
→ 生成并检查配置
→ 检查成功后启动 sing-box
```

Route 可以选择 DIRECT、MANUAL 或 AUTO。只有 DIRECT Route 时同样可以正常启动；未被 Route 引用的 Inbound 不对外监听。

### 3.2 正常启动与运行

```text
sing-box 启动或重启成功
→ MANUAL 从 Default Node 初始化 Current Node
→ AUTO 从 Fallback Node（Default Node）初始化 Current Node
→ 清空 Runtime State 中的检测和切换状态
→ 后台控制循环开始管理 Routed AUTO
```

MANUAL 的 Current Node 由用户管理；AUTO 的 Current Node 由后台控制循环管理。

### 3.3 MANUAL 在线切换

```text
MANUAL 正在运行
→ 用户选择新的 Node
→ 实际切换成功
→ Current Node 更新为新 Node
→ Default Node 同步更新为新 Node
```

切换失败时 Current Node 和 Default Node 均不改变。下一次 sing-box 启动时仍从最新 Default Node 初始化 Current Node。

### 3.4 AUTO 故障恢复

```text
AUTO Current Node 为 Candidate
→ Current Candidate 连续检测失败达到阈值
→ 切换到 Fallback Node
→ 后续控制周期继续检测 Candidate
→ 存在可用 Candidate：切换到其中优先级最高的 Node
→ 长时间无法恢复且持续处于 Fallback：重启 sing-box
→ 开始新的运行周期并重新初始化 Runtime State
```

AUTO 正常运行期间按 Candidate priority 自动选择和恢复，具体规则见第 10 章。

### 3.5 Subscription Sync

```text
管理状态为 stopped
→ 用户执行 Subscription Sync
→ 请求、解析、过滤和校验
→ 生成 Node 变化及级联影响预览
→ 用户确认：一次性更新相关数据
→ 用户取消：不修改数据
```

Subscription Sync 仅允许在 `stopped` 时执行；Subscription Refresh 在 `running` 和 `stopped` 时均允许。

### 3.6 人工修改配置

```text
用户执行 Stop
→ 管理状态进入 stopped
→ 修改 Subscription、Node、Inbound、MANUAL/AUTO 或 Route
→ 用户执行 Start
→ 从最新数据库生成并检查完整配置
→ 检查成功后启动
```

Node Pool 成员不变时，可以在 `running` 或 `stopped` 状态调整 priority。priority 调整只改变后续 AUTO 择优顺序，不立即切换 Current Node。

### 3.7 sing-box 意外退出

```text
管理状态为 running
→ 检测到 sing-box 意外退出
→ 重新生成并检查配置
→ 检查并启动成功：重新初始化 Runtime State
→ 恢复失败：保持 running，并在后续控制周期继续尝试恢复
```

恢复成功后，MANUAL 从 Default Node、AUTO 从 Fallback Node（Default Node）重新初始化 Current Node。

---

## 4. 节点与协议

### 4.1 支持范围

**REQ-NODE-001** 第一版远程节点只支持以下协议：

- VMess；
- VLESS；
- Trojan；
- Shadowsocks；
- Hysteria2。

不支持上述范围之外的远程节点协议。

**REQ-NODE-002** Shadowsocks 节点支持 sing-box 原生提供的插件。

### 4.2 自建节点

**REQ-NODE-003** 用户可以逐项填写协议参数创建自建 Node，也可以粘贴一条受支持的分享 URI，由页面解析并回填表单。

**REQ-NODE-004** 自建 Node 可以查看、修改和删除。

### 4.3 保存与安全

**REQ-NODE-005** Node 必须通过必要字段和协议参数校验后才能保存或导入；无法形成有效代理节点的配置不得保存。

**REQ-NODE-006** Node 凭据、密码、密钥、分享 URI、完整 Subscription URL 等敏感信息不得以明文出现在日志或差异预览中。

---

## 5. sing-box 配置管理

本章定义 sing-box 运行配置相关的数据生成、修改和生效规则。

### 5.1 配置生成与生效

**REQ-CONFIG-001** 数据库保存用于生成 sing-box 配置的业务数据，配置生成时以数据库中的最新业务数据为准。

**REQ-CONFIG-002** 运行中的 sing-box 配置不会因业务数据修改而动态更新；每次启动 sing-box 前，系统必须根据最新数据库重新生成完整配置。

**REQ-CONFIG-003** sing-box 启动前必须完成配置生成和有效性检测，检测通过后才允许替换正式配置并启动 sing-box。

**REQ-CONFIG-004** sing-box 启动时，Current Node 必须根据数据库 Default Node 初始化，不使用上一运行周期的 Current Node：

- MANUAL：Default Node 为启动时的 Current Node；
- AUTO：Default Node 为 Fallback Node，并作为启动初始节点。

**REQ-CONFIG-005** Node Pool priority 属于业务数据，仅保存在数据库中，不参与 sing-box 配置生成，用于 AUTO 模式下 Candidate Node 的自动选择。

### 5.2 Running 状态允许的修改

**REQ-CONFIG-006** 管理状态为 `running` 时，本章所述业务数据仅允许执行本节明确规定的在线修改。

#### 5.2.1 Subscription Refresh

**REQ-CONFIG-007** Subscription Refresh 可以在 `running` 或 `stopped` 状态执行。Refresh 仅更新流量使用情况、到期时间等非 Node 元信息，不新增、删除或修改 Node，也不修改 sing-box 配置。

#### 5.2.2 MANUAL 节点切换

**REQ-CONFIG-008** MANUAL 支持在 `running` 状态切换 Current Node。切换成功时，更新 sing-box 当前选择、运行时 Current Node 和数据库 Default Node，不重新生成 sing-box 配置；切换失败时 Current Node 和 Default Node 均保持不变。

#### 5.2.3 Priority 修改

**REQ-CONFIG-009** MANUAL/AUTO 的 Node Pool priority 支持在线修改。priority 修改后保存数据库，不重新生成 sing-box 配置，不改变 Current Node 或 Default Node，也不立即触发 AUTO 节点切换；后续 AUTO 节点选择使用最新 priority。

### 5.3 Stopped 状态下的配置修改

**REQ-CONFIG-010** 除 5.2 明确允许的在线修改外，Subscription、Node、Inbound、Outbound 和 Route 的业务数据修改均必须在 `stopped` 状态执行。

**REQ-CONFIG-011** 在 `stopped` 状态修改业务数据时，只更新数据库，不生成或检测 sing-box 配置，也不自动启动 sing-box。

**REQ-CONFIG-012** 即使 sing-box 实际进程已经停止，只要管理状态仍为 `running`，REQ-CONFIG-010 规定的业务数据修改仍禁止执行。

**REQ-CONFIG-013** DIRECT 为系统内置、全局唯一的只读 Outbound，不支持新增、修改和删除。

### 5.4 sing-box 配置生成范围与失败处理

#### 5.4.1 Node

**REQ-CONFIG-014** 所有合法 Node 均生成独立 sing-box Outbound；Node 是否被 MANUAL/AUTO 引用，不影响 Node Outbound 的生成。

#### 5.4.2 MANUAL/AUTO

**REQ-CONFIG-015** 仅被 Route 引用的 MANUAL/AUTO 才生成 sing-box Outbound，未被 Route 引用的 MANUAL/AUTO 仅保留业务数据，不生成 sing-box 配置。

#### 5.4.3 DIRECT

**REQ-CONFIG-016** Route 引用 DIRECT 时，必须生成对应的 direct Outbound。

#### 5.4.4 Inbound

**REQ-CONFIG-017** 仅被 Route 引用的 Inbound 才生成 sing-box Inbound，未被引用的 Inbound 仅保留业务数据，不生成 sing-box 配置。

#### 5.4.5 Route

**REQ-CONFIG-018** 所有有效 Route 均生成到 sing-box 配置。

#### 5.4.6 控制配置

**REQ-CONFIG-019** sing-box 配置必须包含 ProxyHub 运行管理所需的控制能力，包括 Node 检测、Current Node 查询和运行时节点切换。

#### 5.4.7 配置失败处理

**REQ-CONFIG-020** 配置生成或有效性检测失败时，不替换正式配置、不启动 sing-box、不回滚数据库，也不使用旧配置启动。

**REQ-CONFIG-021** 系统保留最近一次成功运行的 sing-box 配置用于排错，不用于自动恢复。

---

## 6. Subscription 管理

本章定义 Subscription 的保存、Sync、Refresh、Filter/Exclude 及 Node 更新规则。相关操作的运行状态限制统一遵循第 5 章。

### 6.1 Subscription 基本操作

**REQ-SUB-001** 系统允许维护多个 Subscription。Subscription Sync 仅在用户明确发起时执行，不执行自动或定时 Sync；新建 Subscription 可以暂时不包含 Node。

**REQ-SUB-002** 修改 Subscription URL、Filter 或 Exclude 只保存 Subscription 配置，不修改已有 Node；修改结果在下一次 Subscription Sync 时用于更新 Node。

**REQ-SUB-003** Subscription URL 仅支持具有有效证书的 HTTPS 地址，Subscription Sync 和 Refresh 请求使用 Clash 兼容 User-Agent。

**REQ-SUB-004** Subscription Refresh 使用当前保存的 URL 更新流量使用情况、总流量、到期时间等元信息，不解析或修改 Node。

### 6.2 Filter 与 Exclude

**REQ-SUB-005** Filter/Exclude 仅匹配 Node 的 `name`：

- 匹配忽略大小写；
- 关键词使用逗号或换行分隔，忽略关键词首尾空白及空项；
- 多个 Filter 关键词为 OR，Filter 为空表示不过滤；
- 多个 Exclude 关键词为 OR；
- 同时命中 Filter 和 Exclude 时，以 Exclude 为准；
- 不支持正则表达式或其他复杂筛选规则。

### 6.3 Subscription Sync

**REQ-SUB-006** Subscription Sync 对订阅内容完成解析、Filter/Exclude 和 Node 校验后计算 Node 变化；无效或不支持的 Node 跳过处理，并在差异预览中显示跳过信息。

**REQ-SUB-007** 请求失败、订阅格式无法识别、没有合法 Node 或 Filter/Exclude 后结果为空时，本次 Sync 失败，原有数据保持不变。

**REQ-SUB-008** 同一 Subscription 内以解析得到的完整 `name` 作为 Node 匹配依据，区分大小写且不自动修剪、改写或归一化：

- `name` 相同视为同一 Node，其他字段变化视为修改；
- `name` 变化视为删除旧 Node 并新增新 Node；
- 不同 Subscription 可以存在相同 `name`；
- 同一 Subscription 出现重复 `name` 时，本次 Sync 失败。

### 6.4 差异确认与删除

**REQ-SUB-009** Subscription Sync 必须在修改数据前展示新增、修改、删除和跳过 Node 的差异，以及由 Node 删除引起的 Default Node 替换、MANUAL/AUTO 删除、Route 删除等完整级联影响；用户只能确认或取消整个结果。

**REQ-SUB-010** 用户确认 Sync 后，预览中的 Node 及关联业务数据变更必须整体成功或整体不生效；用户取消时不修改任何数据。

**REQ-SUB-011** 被跳过的 Node 不进入本次 Sync 结果，因此原有对应 Node 可以进入删除预览，并按正常删除规则处理。

**REQ-SUB-012** Subscription Node 仅通过 Subscription Sync 新增、修改或删除，删除所属 Subscription 时一并删除。

**REQ-SUB-013** 删除 Subscription 前必须展示其 Node 及全部级联影响；用户确认后按照与 Node 删除相同的级联规则整体执行。

---

## 7. Inbound、Outbound 与 Route

本章定义 Inbound、MANUAL/AUTO、Route 及其关联关系的业务规则。新增、修改和删除的运行状态限制，以及 priority 在线修改和 MANUAL 在线切换规则，统一遵循第 5 章。

### 7.1 Inbound

**REQ-INBOUND-001** 系统允许创建多个 Inbound，支持 HTTP、SOCKS、Mixed、Shadowsocks 和 VMess。

**REQ-INBOUND-002** 每个 Inbound 独立定义名称、协议、监听地址、监听端口及协议所需的认证参数；Mixed 在同一端口同时支持 HTTP 和 SOCKS。

**REQ-INBOUND-003** 新增或修改 Inbound 时，监听地址和端口不得与已有 Inbound 或 ProxyHub 自身监听端口冲突，存在冲突时禁止保存。

### 7.2 Outbound 通用规则

**REQ-OUTBOUND-001** 用户可以创建、修改和删除 MANUAL/AUTO；每个 MANUAL/AUTO 独立定义名称，包含一个由至少两个不同全局 Node 组成的 Node Pool，并具有一个 Default Node。

**REQ-OUTBOUND-002** Node 可以被多个 MANUAL/AUTO 复用，但在同一个 Node Pool 中只能出现一次；正常编辑 Node Pool 时不得使其少于两个 Node。

**REQ-OUTBOUND-003** 同一 Node Pool 中的 priority 必须唯一，可以不连续，数值越小优先级越高并表示 Node Pool 中的顺序。Node Pool 成员不变时可以按照 REQ-CONFIG-009 在线调整 priority。

**REQ-OUTBOUND-004** Default Node 必须在 Node Pool 中；未指定或被移除时，自动选择 priority 最小的 Node 作为 Default Node。

### 7.3 MANUAL/AUTO

**REQ-OUTBOUND-005** 用户新建 Outbound 时默认为 MANUAL；MANUAL 与 AUTO 可以相互转换，转换时仅修改 `type`；DIRECT 不参与类型转换。

**REQ-OUTBOUND-006** AUTO 不支持人工切换或锁定 Current Node。

**REQ-OUTBOUND-007** MANUAL/AUTO 的 Current Node 切换成功后，中断该 Outbound 上使用旧 Node 的全部已有连接；后续新建或重连的连接使用新的 Current Node。

### 7.4 Route 与级联

**REQ-ROUTE-001** Route 仅建立 Inbound 到指定 Outbound 的流量映射，不支持规则分流；目标 Outbound 必须显式指定为 DIRECT、MANUAL 或 AUTO。

**REQ-ROUTE-002** 删除 Inbound、MANUAL 或 AUTO 时，同时删除引用它的全部 Route。

**REQ-ROUTE-003** 删除一个或多个 Node 时，以全部目标 Node 删除后的 Node Pool 为准；受影响的 MANUAL/AUTO 剩余不足两个 Node 时，级联删除该 MANUAL/AUTO 及引用它的全部 Route；否则保留剩余 Node 的 priority，Default Node 被删除时选择 priority 最小的 Node 作为新的 Default Node。

**REQ-ROUTE-004** Node、Inbound、MANUAL/AUTO 的修改或删除产生级联影响时，必须展示完整影响并经用户确认后执行。

---

## 8. ProxyHub 运行控制与调度

### 8.1 管理状态

**REQ-RUNTIME-001** 管理状态表示 ProxyHub 对 sing-box 的运行管理意图：

- `running`：保持 sing-box 运行，并执行进程守护和 AUTO 控制；
- `stopped`：不要求 sing-box 运行，不执行进程守护和 AUTO 控制。

管理状态与实际进程状态相互独立。

运行控制遵循以下规则：

- Start：生成并检查配置，成功启动 sing-box 后进入 `running`，失败时保持 `stopped`；
- Stop：停止 sing-box 并进入 `stopped`；
- Restart：执行 Stop 后重新 Start；
- 手动 Stop 状态不跨 ProxyHub 自身重启持久化。

### 8.2 ProxyHub 启动

**REQ-RUNTIME-002** ProxyHub 启动时，Settings 加载及校验成功、sing-box 二进制存在且数据库中至少有一条 Route 时，自动生成并检查配置，检查通过后启动 sing-box，成功后进入 `running`。

Settings 异常时终止 ProxyHub 启动。Settings 正常但其他启动条件不满足、配置检查失败或 sing-box 启动失败时，ProxyHub Web 仍正常运行，管理状态保持 `stopped`。

### 8.3 sing-box 运行周期

**REQ-RUNTIME-003** 每次 sing-box 成功启动或重启后开始新的运行周期，并重新初始化 Runtime State：

- 清除所有 Node 的健康状态及检测信息；
- 被 Route 引用的 MANUAL/AUTO 从数据库 Default Node 初始化 Current Node；AUTO 的 Default Node 即 Fallback Node；
- AUTO 连续失败次数归零；
- 清除 Fallback 和 Priority Recovery 相关计时。

启动前不检测 Candidate Node，也不根据历史健康状态改变初始选择。

### 8.4 后台控制循环与调度

**REQ-RUNTIME-004** ProxyHub 运行一个后台控制循环，每个控制周期串行执行：

```text
if 管理状态 == running:
    if sing-box 未运行:
        尝试恢复 sing-box
    else:
        逐个处理 Routed AUTO

结束本控制周期
等待基础控制间隔
开始下一周期
```

进程恢复无论成功或失败，均结束本周期。

基础控制间隔（Control Interval）从当前控制周期结束后开始计算，等待结束后开始下一周期；不补跑执行期间错过的控制周期。

### 8.5 进程守护

**REQ-RUNTIME-005** 管理状态为 `running` 且 sing-box 未运行时，重新生成并检查配置，检查通过后尝试启动 sing-box：

- 恢复成功：开始新的运行周期；
- 恢复失败：记录错误，保持 `running`，后续控制周期继续尝试恢复。

### 8.6 AUTO 控制

**REQ-RUNTIME-006** 仅在管理状态为 `running` 且 sing-box 正常运行时，逐个处理 Routed AUTO。

### 8.7 运行控制锁

**REQ-RUNTIME-007** 后台控制周期以及可能改变管理状态、sing-box 实际进程状态、运行配置或 Runtime State 的控制操作串行执行，包括 Start、Stop、Restart、结构配置写操作、priority 调整、MANUAL 在线切换以及 sing-box 下载或升级替换。

- 后台控制周期从进程守护到 AUTO 处理结束期间，不与其他运行控制操作并发执行；
- 结构配置写操作开始时管理状态必须为 `stopped`；priority 调整在 `running` 和 `stopped` 时均可执行；
- Restart 的 Stop 和 Start 连续执行，中间不插入其他运行控制操作；
- Subscription Refresh、Settings 保存和人工检测可以与运行控制操作并发执行。

---

## 9. 节点健康检测

### 9.1 检测方式与流程

**REQ-HEALTH-001** AUTO 控制触发的 Node 检测和用户主动发起的人工检测使用相同的单 Node 检测流程，依次执行 TCP 检测和 URL 检测，URL 检测不受 TCP 检测结果影响。

### 9.2 TCP 检测

**REQ-HEALTH-002** TCP 检测用于检查 Node 的 TCP 连接情况并测量连接延迟，检测结果不参与 Node 最终健康判断。

### 9.3 URL 检测

**REQ-HEALTH-003** URL 检测通过被检测 Node 的代理流量访问 HTTPS 测试 URL，根据 HTTP 2xx 状态码和响应延迟判断 URL 是否可用，并记录响应延迟。

### 9.4 Node 健康状态

**REQ-HEALTH-004** 每个 Node 保存最近一次完成检测的健康状态及检测信息，包括 TCP 和 URL 检测结果、检测时间和失败原因。Node 完成检测后，根据 URL 检测结果更新健康状态。

### 9.5 检测执行与状态更新

**REQ-HEALTH-005** 单个 Node 的 TCP 和 URL 检测全部完成后，一次性更新其健康状态和检测信息。

**REQ-HEALTH-006** AUTO 检测和人工检测相互独立，可以并发执行，并分别控制批量检测的并发数量。人工检测由用户触发，不参与后台控制循环的串行执行。

**REQ-HEALTH-007** 同一 Node 存在并发检测时，各检测完成后正常更新其健康状态和检测信息，后完成覆盖先完成。

**REQ-HEALTH-008** AUTO 控制不使用 Node 已保存的健康状态作为当前控制依据，每次需要判断 Node 状态时执行检测，并使用本次检测结果进行后续控制。

### 9.6 人工检测

**REQ-HEALTH-009** sing-box 进程正常运行时，用户可以主动发起单个或批量 Node 健康检测。

**REQ-HEALTH-010** 人工检测只更新 Node 健康状态和检测信息，不修改 AUTO 的 Current Node、连续失败次数及恢复相关状态，也不触发 AUTO 控制。

---

## 10. AUTO 故障切换

### 10.1 AUTO 控制规则

**REQ-FAILOVER-001** 只有 Routed AUTO 执行 AUTO 控制。AUTO 的 Default Node 为 Fallback Node，其他 Node 为 Candidate Node；Candidate Node 使用 Node Pool priority 参与自动选择，数值越小优先级越高。

**REQ-FAILOVER-002** AUTO 按 priority 选择 Candidate Node 时，使用当前 Node Pool priority。priority 在线修改不立即触发 AUTO 节点切换。

AUTO 控制流程：

```text
逐个处理 Routed AUTO
    ↓
Current Node 是否为 Fallback Node？
    ├── 是 → 执行 Fallback Recovery
    │        ↓
    │        是否成功切换到 Candidate Node？
    │        ├── 是 → 处理下一个 AUTO
    │        └── 否 → Fallback 持续时间是否超时？
    │                 ├── 否 → 处理下一个 AUTO
    │                 └── 是 → 重启 sing-box，本控制周期结束
    │
    └── 否 → 检测 Current Candidate
             ↓
             连续失败是否达到阈值？
             ├── 是 → 尝试切换到 Fallback Node
             │        ├── 成功 → 本 AUTO 处理结束
             │        └── 失败 → 重启 sing-box，本控制周期结束
             │
             └── 否 → 存在更高优先级 Candidate 且 Priority Recovery 间隔已到期？
                      ├── 否 → 处理下一个 AUTO
                      └── 是 → 执行 Priority Recovery
                               ├── 存在可用 Candidate → 尝试切换，失败按 10.7 处理
                               └── 无可用 Candidate → 保持 Current Node
```

- Fallback Recovery：当前处于 Fallback Node 时，检测全部 Candidate Node 并尝试恢复到可用 Candidate 的过程。
- Priority Recovery：当前处于 Candidate Node 时，检测优先级更高的 Candidate Node 并尝试恢复到更高优先级节点的过程。

本章由 AUTO 触发的 sing-box 重启保持管理状态为 `running`；重启失败时记录错误，后续控制周期由进程守护继续恢复。无论重启成功或失败，本控制周期均结束。

### 10.2 Runtime State

**REQ-FAILOVER-003** 每个 AUTO 在当前运行周期中维护的 Runtime State 包括 Current Node、Current Candidate 连续失败次数、Fallback 持续时间和 Priority Recovery 计时。

**REQ-FAILOVER-004** Current Node 为 Fallback 时累计 Fallback 持续时间，离开 Fallback 后停止累计并重置该时间。

### 10.3 Current Candidate 检测与故障切换

**REQ-FAILOVER-005** Current Node 为 Candidate 时，每个控制周期检测一次 Current Candidate 的可用性；检测成功则连续失败次数清零，检测失败则连续失败次数加一。

**REQ-FAILOVER-006** Current Candidate 连续失败达到配置阈值时，尝试切换到 Fallback Node。切换成功后，Current Node 更新为 Fallback Node，连续失败次数清零，并开始累计 Fallback 持续时间；该 AUTO 本控制周期处理结束。

### 10.4 Fallback Recovery

**REQ-FAILOVER-007** Current Node 为 Fallback 时，每个控制周期执行 Fallback Recovery。检测完成后，在可用 Candidate 中选择优先级最高的 Node 并切换；没有可用 Candidate 时保持 Fallback。

**REQ-FAILOVER-008** 从 Fallback 成功切换到 Candidate 后，更新 Current Node，连续失败次数清零，停止累计并重置 Fallback 持续时间，并从切换成功时间开始计算 Priority Recovery 间隔。

### 10.5 Priority Recovery

**REQ-FAILOVER-009** Current Node 为 Candidate 且不是 Candidate Node 中优先级最高的 Node 时，达到 Priority Recovery 间隔后执行 Priority Recovery。

Priority Recovery 仅检测优先级高于 Current Candidate 的 Candidate Node。检测完成后，在可用 Candidate 中选择优先级最高的 Node 并切换；不存在可用 Candidate 时保持 Current Candidate。

**REQ-FAILOVER-010** Priority Recovery 成功切换后，连续失败次数清零，并从切换成功时间重新计算 Priority Recovery 间隔；未发生切换时，从本次检测完成时间重新计算该间隔。

### 10.6 Fallback 超时重启

**REQ-FAILOVER-011** Current Node 为 Fallback 时，在每个控制周期完成 Fallback Recovery 后判断 Fallback 持续时间；达到 Fallback 重启超时阈值且仍处于 Fallback 时，重启 sing-box，并结束当前控制周期。

### 10.7 节点切换失败

**REQ-FAILOVER-012** 只有节点实际切换成功后才更新 Current Node。切换失败时：

- Current Candidate 切换到 Fallback 失败：重启 sing-box，并结束当前控制周期；
- Fallback 切换到 Candidate 失败：保持 Fallback，继续累计 Fallback 持续时间；
- Priority Recovery 切换失败：保持 Current Candidate，并从本次检测完成时间重新计算 Priority Recovery 间隔。

---

## 11. 管理页面与认证

### 11.1 页面范围

**REQ-UI-001** 桌面页面提供 Subscription、Node、Inbound、Outbound、Route、Settings、管理状态、sing-box 实际进程状态、关键日志和 sing-box 管理功能。

**REQ-UI-002** 桌面页面支持 Subscription、Node、Inbound、Outbound、Route 和 Settings 的管理操作，以及 Subscription Sync、Subscription Refresh、Start、Stop、Restart、关键日志查看、日志下载和 sing-box 管理操作。

**REQ-UI-003** 桌面页面支持单个或批量 Node 健康检测、MANUAL Current Node 切换和 MANUAL/AUTO Node Pool priority 调整。

**REQ-UI-004** 移动页面提供管理状态、sing-box 实际进程状态、Inbound 和 Outbound 展示及 Node 健康状态展示，并支持 MANUAL Current Node 切换和 MANUAL/AUTO Node Pool priority 调整。

### 11.2 登录

**REQ-AUTH-001** 登录使用用户名和密码。默认用户名为 `admin`，默认密码为空；密码为空时不启用登录认证。

**REQ-AUTH-002** 密码非空时，桌面页面、移动页面、全部内部 API 和日志下载均必须认证。系统提供登录和退出功能。

**REQ-AUTH-003** 密码只保存安全哈希，不保存或记录明文。修改用户名或密码后立即使既有会话失效；认证启用时要求重新登录。

---

## 12. Settings、日志和默认值

### 12.1 Settings 行为

**REQ-SETTINGS-001**

所有应用设置必须采用统一持久化机制保存。Settings 用于保存应用配置参数，不用于保存运行状态或业务运行数据。各配置项必须定义其默认值和修改方式。

**REQ-SETTINGS-002**

ProxyHub 启动时必须加载持久化设置。首次运行或持久化设置不存在时，系统应使用内置默认值创建有效配置。

**REQ-SETTINGS-003**

通过管理功能修改 Settings 时，保存请求开始时管理状态必须为 `stopped`。设置保存不取得运行控制锁。保存前必须完成完整校验，仅在校验通过后更新设置；校验失败时原有设置保持不变，非法设置不得生效。

**REQ-SETTINGS-004**

Settings 保存不自动启动 sing-box。通过管理功能修改的设置，除 Username 和 Password 外，在下一次 sing-box Start 后生效；Start 使用开始时已成功保存的设置。Username 和 Password 保存后立即生效，并按 REQ-AUTH-003 处理既有会话。

**REQ-SETTINGS-005**

直接修改持久化配置文件的内容仅在 ProxyHub 下一次启动时加载并生效。

**REQ-SETTINGS-006**

持久化设置缺少已定义配置项时，系统应仅对缺失项使用对应默认值补全，并继续执行完整校验；补全后的完整配置应自动写回持久化设置。回写失败时，报告错误并终止启动，不使用未成功持久化的补全配置继续运行。

当持久化设置无法加载、格式错误、包含非法配置项或校验失败时，ProxyHub 必须终止启动，不启动 Web 服务或 sing-box。系统不得使用默认值替代已存在但非法的配置项。

**REQ-SETTINGS-007**

用户密码不得以明文形式持久化保存。认证所需的敏感密钥应独立管理，不作为普通应用设置保存或展示。

### 12.2 Settings 配置项与默认值

“管理修改”表示配置项是否支持通过 ProxyHub 管理功能进行修改；此类修改遵循 12.1 的状态限制和生效规则。不支持管理修改的配置项只能直接修改持久化配置文件，并在 ProxyHub 下一次启动时加载生效。

| Setting | 默认值 | 管理修改 | 备注 |
|---|---:|:---:|---|
| Control Interval | 15 秒 | 是 | 后台控制循环周期等待时间 |
| TCP Timeout | 3 秒 | 是 | 单个 Node TCP 检测超时时间 |
| URL Timeout | 5 秒 | 是 | 单个 Node URL 检测超时时间 |
| Test URL | `https://www.gstatic.com/generate_204` | 是 | 所有 Node 共用的 URL 健康检测地址 |
| Max Concurrency | 10 | 是 | AUTO 检测或人工批量检测中的最大并发 Node 数量 |
| Failure Threshold | 3 次 | 是 | Current Candidate 连续 URL 检测失败达到该次数后切换到 Fallback |
| Priority Recovery Interval | 60 秒 | 是 | Candidate 优先级恢复检测间隔 |
| Fallback Restart Timeout | 300 秒 | 是 | AUTO 持续处于 Fallback 时触发 sing-box 重启的超时时间 |
| Web Listen Address | `127.0.0.1` | 否 | ProxyHub Web 监听地址 |
| Web Port | 8080 | 否 | ProxyHub Web 监听端口 |
| Username | `admin` | 是 | 登录用户名 |
| Password | 空 | 是 | 为空时关闭认证；仅保存密码安全哈希 |

### 12.3 日志

**REQ-LOG-001** 系统应记录足够的运行和排错信息。桌面页面只显示最近关键事件，不提供完整日志浏览，但允许下载日志文件。

**REQ-LOG-002** Node 切换、Fallback 持续超时、人工检测、sing-box 启动/停止/重启、配置生成和升级属于关键事件。

---

## 13. sing-box 下载、升级与部署

### 13.1 下载与升级

**REQ-UPGRADE-001**

ProxyHub Web 在 sing-box 二进制不存在时仍应正常运行。sing-box 二进制不存在时，管理状态保持 `stopped`。

**REQ-UPGRADE-002**

当 sing-box 二进制存在时，页面应显示检测到的本地当前版本；二进制不存在时显示“未安装”。

管理状态为 `stopped` 时，允许执行远程版本检查以及下载或升级操作。管理状态为 `running` 时禁止执行上述操作，仅显示本地当前版本。下载或升级成功后保持 `stopped` 状态，不自动启动 sing-box。

**REQ-UPGRADE-003**

sing-box 下载和升级必须采用失败保护机制：

1. 下载内容必须先保存到临时文件；
2. 完成下载后必须验证文件完整性、架构、可执行性以及版本信息；
3. 验证通过后才能替换正式二进制文件；
4. 任一步失败时必须保留原有二进制文件，记录错误日志，并向发起操作的页面返回失败提示。

### 13.2 部署

**REQ-DEPLOY-001**

第一版支持 Docker Compose 和 Ubuntu Python/venv 两种部署方式，并保持配置格式一致。

**REQ-DEPLOY-002**

第一版支持 Ubuntu 20.04 及以上版本以及 amd64 架构 CPU。不要求支持 Windows、macOS、其他 Linux 发行版、32 位 x86 或 arm64 架构。

---

## 14. 最低可靠性要求

**REQ-REL-001**

所有运行控制锁的使用与串行化规则统一遵循 REQ-RUNTIME-007。第一版不建立跨进程锁或分布式事务。

**REQ-REL-002**

Subscription Sync 的请求、解析或预览失败时原数据不变；用户确认后，Subscription（适用时）、Node、Default Node 自动替换、MANUAL/AUTO 更新或删除和 Route 删除作为一个业务事务完成。

**REQ-REL-003**

删除 Subscription、Node、Inbound、MANUAL、AUTO 或 Route 前显示简单确认；涉及级联时显示受影响对象以及必要的 Default Node 自动替换。删除 MANUAL/AUTO 时必须删除引用它的 Route，不得把 Route 自动或静默改为系统内置 DIRECT。

**REQ-REL-004**

ProxyHub Web 已启动时，sing-box 启动或配置检查失败由前端显示简单错误和关键事件，详细信息写入可下载日志。Settings 文件异常导致 ProxyHub 无法启动时按 REQ-SETTINGS-006 通过启动输出和正常日志渠道报告。不建立大型结构化错误模型或专项错误页面。

**REQ-REL-005**

第一版不承诺配置更新无中断，允许人工 Stop、修改、Start 过程中出现短暂停顿。

---

## 15. 第一版明确不做

第一版不实现：

- 多用户、角色和权限管理；
- 多台 ProxyHub 主机集中管理；
- 多 sing-box 实例或多代理引擎；
- 多条 URI 批量导入；
- 节点文件批量导入；
- Xray、sslocal 和 TUIC；
- 面向第三方的稳定公共 API；
- 多 Web worker、多进程共享状态；
- 分布式任务队列、任务历史和任务恢复；
- 自动执行 Subscription Sync；
- 配置热重载或运行时动态应用配置；
- 完整规则路由、分流规则和通用 sing-box 配置编辑器；
- 历史健康、历史延迟、流量统计和分析报表；
- 消息推送；
- sing-box 后台自动升级和复杂版本回滚；
- v1/v2 数据库、Settings、运行状态或内部 API 兼容迁移；
- 企业级高可用、复杂安全风控和所有理论异常的专项恢复机制。
