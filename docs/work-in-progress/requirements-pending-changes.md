# ProxyHub 个人版第一版需求待修改项

本文记录评审过程中已确认、但尚未写入 `docs/01-requirements.md` 的修改项。本文不是正式需求依据；正式需求仍以 `docs/01-requirements.md` 为准。

## 待修改

### 简化新建 Outbound 的节点角色选择

- 新建 MANUAL 或 AUTO 时，用户只需要选择 Node 并确定 Node Pool 顺序，不需要另外指定 Current Node 或 Fallback Node。
- Node Pool 保存并整理为连续、唯一的 priority 后，默认使用第一个 Node，即 `priority = 1` 的 Node：
  - 新建 MANUAL 时，该 Node 自动成为初始持久化 Current Node；
  - 新建 AUTO 时，该 Node 自动成为 Fallback Node。
- 创建完成后，用户仍可手动修改 MANUAL 的 Current Node 或 AUTO 的 Fallback Node；修改时继续遵循正式需求中已有的运行状态限制和保存规则。
- 本项只简化新建 Outbound 的操作流程，不修改 Node Pool 排序、priority、MANUAL/AUTO 运行策略、type 转换或自动故障切换规则。
- 正式合并时重点同步检查 `REQ-OUTBOUND-007`、`REQ-OUTBOUND-008`、新建 Outbound 页面流程及相关验收描述，删除“新建 AUTO 时必须明确指定 Fallback Node”的要求。

### 简化 Route 小节标题

- 将 `6.4 Route、DIRECT 与级联删除` 简化为 `6.4 Route`。
- 本项只调整小节标题，不修改本节关于 Route 引用关系、DIRECT 作为 Route 目标以及相关级联删除的需求内容。

### 只为被 Route 引用的 Outbound 生成 selector

- sing-box 配置只包含被至少一条 Route 引用的 MANUAL/AUTO 对应的 selector；未被 Route 引用的 MANUAL/AUTO 只保存于数据库，不生成 selector。
- 未被 Route 引用的 MANUAL/AUTO 不执行 Current Node 运行时切换、健康控制或自动故障切换。其 Node Pool、priority、MANUAL 的 Current Node 和 AUTO 的 Fallback Node 仍正常持久化。
- 后续为 MANUAL/AUTO 绑定 Route 时，继续遵循 Route 只能在 sing-box stopped 时修改的限制，并在下一次 Start 时生成对应 selector。
- 所有合法的全局 Node 仍按现有需求生成独立出站，供 Node 健康检测使用，不受本项影响。
- 正式合并时修改 `REQ-CONFIG-005` 中“所有已保存的 MANUAL/AUTO 对应的 selector，包括未被 Route 引用者”，并同步检查 MANUAL 人工切换、AUTO 控制、页面状态和配置生成相关描述。

### 将 sing-box 字段级配置映射移至模块设计

- 从正式需求的 `REQ-CONFIG-005` 中移除 selector 的 `outbounds`、`default`、`interrupt_exist_connections`、系统内置 direct tag 和 cache file 处理方式等字段级实现描述。
- 需求中继续保留并由现有相关条款规定以下业务行为：
  - MANUAL/AUTO 的 Node 顺序遵循 priority；
  - MANUAL 启动后使用持久化的 Current Node；
  - AUTO 启动或重启后从 Fallback Node 初始化；
  - 历史运行状态不得覆盖 MANUAL/AUTO 的初始化选择；
  - Current Node 切换后中断已有连接，使后续重连使用新节点；
  - Route 选择 DIRECT 时流量直接访问目标。
- 在配置生成章节只保留设计边界：MANUAL/AUTO、DIRECT、Node 和 Route 到 sing-box 配置对象、tag 及字段的具体映射由 sing-box 模块设计规定，实现必须满足正式需求中的 priority、Current Node、Fallback Node、启动初始化、连接中断和 DIRECT Route 行为。
- 正式合并时检查 `REQ-OUTBOUND-005`、`REQ-OUTBOUND-003`、`REQ-RUNTIME-004` 和 Route 相关需求已完整承载上述业务行为，避免删除字段级描述时遗漏可验收要求。

### 将第 8 章重构为 ProxyHub 运行任务

- 将第 8 章标题由 `sing-box 生命周期` 改为 `ProxyHub 运行任务`，只描述启动任务和后台控制任务。

#### 8.1 启动任务

- ProxyHub 启动时检查 sing-box 二进制、Settings 和有效 Route。满足启动条件时生成并检查配置，然后自动启动 sing-box；条件不满足或配置检查失败时，只启动 Web 并保持 sing-box stopped。
- 手动 Stop 只在当前 ProxyHub 运行期间有效，不持久化；下次 ProxyHub 启动时重新判断启动条件。
- 每次 sing-box 实际启动或重启成功后，清空相关临时状态，MANUAL 恢复持久化的 Current Node，Routed AUTO 从 Fallback Node 初始化。
- Start、Restart 的配置生成和检查引用 `REQ-CONFIG-004`，不在第 8 章重复展开；selector 的具体初始化字段移至 sing-box 模块设计。

#### 8.2 后台控制任务

- ProxyHub 只运行一个串行后台控制循环，每个周期严格按以下顺序执行：
  1. sing-box 进程守护；
  2. AUTO 故障检测与切换；
  3. 全局 Node 扫描已启用且到期时，执行全局扫描。
- sing-box 处于期望 running 状态但进程异常退出时，使用当前正式配置重启；用户手动 Stop 或启动失败后不执行守护重启。
- AUTO 故障检测与切换只处理 Routed AUTO，具体故障判断、切换和恢复规则由第 10 章规定。
- 全局 Node 扫描可以通过 Settings 开启或关闭；扫描结果只更新 Node 健康状态、页面展示和日志，不参与 AUTO 调度，也不修改任何 AUTO 控制状态。
- 本周期全部处理完成后等待配置的基础间隔，再开始下一周期；不同控制周期和检测批次不得重叠。
- 单一串行后台控制循环只限制三个任务之间的调度和状态修改保持串行，不取消单个 Node 检测批次内部现有的受限并发能力。
- 第 9 章只规定 Node 检测流程和健康状态，第 10 章只规定 AUTO 的故障判断、切换与恢复行为。正式合并时删除或改写 `REQ-HEALTH-008`、`REQ-FAILOVER-001` 和 `REQ-FAILOVER-002` 中重复的外层后台调度描述；AUTO 内部处理顺序仍保留在第 10 章。
- Fallback 持续超时后的恢复性重启由第 10 章规定，不在第 8 章重复展开。

### 精简 Node 健康检测步骤

- 整体精简 `REQ-HEALTH-001`，删除受支持协议、Hysteria2、服务器地址和端口等重复或实现层描述，只保留统一检测流程。
- 建议改为：`所有 Node 均可执行健康检测。每次检测先执行 TCP 检测，再执行 URL 检测，并分别记录 tcp delay 和 url delay；TCP 检测无论成功或失败都继续执行 URL 检测。`
- 不为任何协议增加单独说明或检测特判。
- 本项只简化描述，不改变现有 Node 检测范围、健康结果判定和全局 Node 扫描规则；delay 的超时取值按“精简 Node 健康状态”待修改项调整。

### 精简 Node 健康状态

- 将 `9.2 内存状态` 改为 `9.2 Node 健康状态`，只保留状态字段、完整检测后更新、不持久化以及人工检测与 AUTO 控制状态的边界。
- 每个 Node 在内存中保存最近一次已完成检测的 `result`、`tcp delay`、`url delay`、`last checked time` 和 `failure reason`。
- delay 统一使用以下取值：
  - 尚未检测时为空；
  - 检测成功时记录实际毫秒数；
  - 检测超时时记录为 `-1`；
  - 其他未取得有效 delay 的情况为空。
- TCP 超时时继续执行 URL 检测；`tcp delay = -1` 不影响最终健康结果。`url delay = -1` 表示 URL 检测超时，此时 `result = unavailable`。
- TCP 和 URL 检测全部完成后，一次性更新 Node 健康状态；检测期间继续展示最近一次已完成的结果。健康状态不写入数据库，ProxyHub 或 sing-box 重启后重新检测。
- 人工检测可以更新 Node 健康状态，但不修改 AUTO 的连续失败次数、Current Node、Fallback 状态或其他自动控制状态。Node 健康状态与 AUTO 控制状态分别管理。
- 删除或移至模块设计的内容包括：检测临时数据的实现过程、不增加 `checking` 字段、调度逻辑如何记录检测执行状态，以及跨周期缓存、有效期和复杂复用规则等实现说明。

### 精简全局 Node 扫描

- 将 `REQ-HEALTH-008` 从第 9 章合并到 `8.2 后台控制任务`，不再在健康检测章节单独规定后台调度。
- 精简后的全局扫描行为为：`全局 Node 扫描可以通过 Settings 开启或关闭。启用后，系统按配置间隔检测全部 Node；检测结果只用于更新 Node 健康状态、页面展示和日志，不参与 AUTO 调度，也不修改任何 AUTO 控制状态。`
- 本项只简化描述，不改变全局扫描的开关、检测范围、执行间隔或结果用途。
