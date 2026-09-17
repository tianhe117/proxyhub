# ProxyHub 设计 TODO

本文记录需求确认后需要在模块设计阶段明确的实现事项。本文不是正式需求依据，设计结论不得改变 `docs/01-requirements.md` 规定的产品行为。

---

# 1. sing-box 模块设计

## 1.1 Outbound、Route 与 sing-box 配置映射

设计时需要明确并形成可验证样例：

* 全局 Node 到 sing-box 独立 Outbound 的字段映射、tag 生成和唯一性规则；
* 被 Route 引用的 MANUAL/AUTO 到 sing-box selector 的映射，以及未被 Route 引用的 MANUAL/AUTO 不生成对应运行对象的处理；
* Node Pool 到 selector 节点列表的映射及顺序规则；
* AUTO 择优使用数据库最新 priority，而不依赖 selector 自身顺序的实现方式；
* MANUAL/AUTO 的 Default Node 到启动时 Current Node 初始选择的映射；
* AUTO 将 Default Node 作为 Fallback Node 的实现方式；
* DIRECT 对应的系统内置 direct Outbound、保留 tag 及 Route 到该 tag 的映射；
* Inbound、Route、selector、Node 独立 Outbound 和 DIRECT tag 的完整引用关系；
* sing-box cache file 是否启用，以及如何保证缓存状态不会恢复上一运行周期的 Current Node 或覆盖 Default Node 初始化规则；
* 配置生成、`sing-box check`、正式配置原子替换和 sing-box 启动之间的执行顺序；
* 最新成功运行配置的保留位置、更新时机及故障排查使用方式。

需要至少覆盖以下配置样例：

* 仅 DIRECT Route；
* MANUAL Route；
* AUTO Route；
* 多条 Route 共享同一个 MANUAL/AUTO；
* 未被 Route 引用的 MANUAL/AUTO；
* 多个 Inbound 和 Route 混合使用。

---

## 1.2 Current Node 运行时控制

设计时需要明确：

* MANUAL 在线切换的前提检查及校验位置：

  * 管理状态为 `running`；
  * MANUAL 被 Route 引用且已生成运行对象；
  * sing-box 实际进程及切换能力可用；
  * 目标 Node 属于对应 Node Pool；

* 上述前提不满足时拒绝切换、保持 Current Node 和 Default Node 不变的处理，以及页面操作可用性和 API 失败返回；

* sing-box Current Node 查询、切换及切换成功确认的调用方式；

* sing-box 控制能力不可用或切换失败时的错误处理；

* MANUAL 切换成功后 Runtime State 中的 Current Node 与数据库 Default Node 的一致性处理；

* 按 REQ-OUTBOUND-007 实现 MANUAL/AUTO 切换成功后中断该 Outbound 上使用旧 Node 的已有连接，使后续新建或重连连接使用新的 Current Node，并覆盖多条 Route 共享同一个 Outbound 的场景；

* Current Node 查询结果与本地 Runtime State 不一致时的处理方式。

---

## 1.3 priority 在线修改

设计时需要明确：

* Node Pool priority 的持久化结构和唯一性约束；
* 新建 Node Pool 时初始 priority 的生成方式；
* 插入、删除和重新排序时 priority 的分配策略；
* 在允许 priority 不连续的前提下避免无意义整体重编号的策略；
* 在线调整多个 priority 时避免中间状态违反唯一约束的更新方式；
* priority 修改与 AUTO 后台控制循环并发时，保证后续节点选择读取最新 priority 的方式。

具体 priority 数值分配算法属于设计实现，不写入正式需求。

---

# 2. Subscription 模块设计

## 2.1 Subscription 请求与解析

设计时需要明确：

* 第一版支持的订阅内容格式清单、格式识别方式和解析流程；
* 各支持格式的可验证样例及不支持格式的失败样例；
* Clash 兼容 User-Agent 的具体值及请求头组织方式；
* Subscription Refresh 所需流量、总流量、到期时间等元信息的获取和解析方式；
* Subscription Sync 与 Refresh 共用和独立的请求处理逻辑；
* Subscription URL 请求错误、格式错误和 parser 错误的内部分类及对外表达；
* Filter/Exclude、Node 校验和差异计算的处理顺序；
* Subscription Node `name` 身份匹配规则的具体实现，确保不会发生自动修剪、改写或 Unicode 归一化。

---

## 2.2 差异预览与事务

设计时需要明确：

* Subscription Sync 差异预览的数据结构；
* 新增、修改、删除和跳过 Node 的预览数据组织方式；
* Node 删除产生的 Default Node 替换、MANUAL/AUTO 删除和 Route 删除的级联影响计算方式；
* 用户确认前后数据发生变化时的一致性处理策略；
* 用户确认后的事务边界及失败回滚方式；
* Subscription 删除与 Subscription Sync 共用级联处理逻辑的方式。

---

# 3. 业务数据与级联处理

设计时需要明确：

* 一次删除多个 Node 时，先计算全部目标 Node 删除后的最终 Node Pool，再统一执行 Default Node 替换和 MANUAL/AUTO 删除的实现方式；
* Default Node 被删除后选择最小 priority Node 的实现方式；
* MANUAL/AUTO 删除后级联删除全部引用 Route 的处理方式；
* Node、Inbound、MANUAL/AUTO 删除产生级联影响时的预览和确认数据结构；
* 普通 Node、Inbound、MANUAL/AUTO 删除及 Subscription Sync、Subscription 删除的事务边界；
* 一次操作涉及的删除、Default Node 替换、Node Pool 更新及 Route 级联删除使用一个数据库事务完成，失败时整体回滚；
* 按 REQ-SUB-012 在业务入口禁止直接新增、修改或删除 Subscription Node；
* 区分从 Node Pool 移除成员与删除全局 Node；
* Node Pool 正常编辑与全局 Node 删除导致 Node Pool 缩减两种场景的处理边界。

级联处理采用普通数据库事务，不增加额外状态机、任务恢复或复杂补偿机制。

---

## 3.1 Inbound 监听冲突

设计时需要明确：

* Inbound 监听地址和端口冲突的判断方式；
* `0.0.0.0`、`127.0.0.1`、具体网卡地址及 IPv6 地址之间的冲突判断；
* Inbound 与 ProxyHub 自身监听端口的冲突检查范围；
* 冲突检查的执行位置和错误返回方式。

---

# 4. Node 协议与输入映射

设计时需要明确并形成可验证样例：

* VMess、VLESS、Trojan、Shadowsocks 和 Hysteria2 的字段映射、合法组合及版本兼容范围；
* Reality、uTLS fingerprint、WebSocket、gRPC 和 HTTP/2 等能力适用的协议、字段组合和校验规则；
* 当前集成 sing-box 可直接处理的 Shadowsocks plugin 范围、字段映射和校验方式，以及不安装或管理额外插件程序的实现边界；
* 单条分享 URI 的解析、字段回填和错误处理；
* Node 必要字段、端口和协议参数的保存校验规则。

---

# 5. 敏感信息处理

设计时需要明确：

* Node 凭据、分享 URI、完整 Subscription URL 和 parser 原始输入等敏感信息的识别范围；
* 日志、错误信息和差异预览的统一脱敏位置及处理方式；
* 差异预览允许展示的安全字段和失败原因；
* HTTP、parser 和 sing-box 底层错误向用户展示或写入日志前的清理规则；
* 对脱敏规则形成可验证样例和测试用例。

---

# 6. Node 健康检测设计

## 6.1 单 Node 检测

设计时需要明确：

* TCP 检测的实现方式、连接目标、超时和错误分类；
* TCP 连接延迟的计算方式；
* URL 检测通过指定 Node 实际代理流量访问测试 URL 的实现方式；
* URL 检测依据 HTTP 2xx 状态码和响应延迟判定成功或失败的具体规则，以及超时和其他错误的内部表达；
* TCP 和 URL 检测结果的数据结构；
* 单次 Node 检测完成后的结果组织方式。

---

## 6.2 Node 健康状态

设计时需要明确：

* Node 健康状态及检测信息的 Runtime State 数据结构；
* 健康状态内部表达方式；
* TCP 和 URL 检测结果、检测时间、失败原因的字段设计；
* 延迟、超时、失败等情况的字段表达方式；
* 新运行周期开始时 Node 健康状态及检测信息的初始化方式；
* 检测完成后一次性更新健康状态和检测信息的实现方式。

---

## 6.3 检测并发

设计时需要明确：

* 每次 AUTO 检测和每个人工检测请求分别按配置限制批量并发数量的实现方式；
* AUTO 检测与人工检测并发执行时的任务组织方式；
* 多个人工检测请求同时执行时的并发控制方式；
* 同一 Node 存在多个并发检测时，按照完成顺序更新健康状态和检测信息的实现方式；
* 检测任务执行期间 Node 被删除时，检测结果回写处理；
* 检测任务跨 sing-box 运行周期完成时，旧检测结果丢弃处理；
* sing-box 不可用、检测失败或异常退出时的结果处理。

---

## 6.4 AUTO 与人工检测隔离

设计时需要明确：

* AUTO 控制直接使用本次检测结果进行判断，不读取 Node 已保存健康状态作为当前控制依据的实现方式；
* 人工检测只更新 Node 健康状态和检测信息，不影响 AUTO Current Node、连续失败次数及恢复相关状态；
* 人工检测不参与后台控制循环串行执行的模块边界；
* AUTO 检测和人工检测共用单 Node 检测实现，同时保持控制逻辑和并发控制独立。

---

# 7. 后续章节设计同步

AUTO、Settings 和 API/Page 需求冻结后，再补充对应模块设计，重点包括：

* ProxyHub 管理状态与 sing-box 进程生命周期；
* Start、Stop、Restart、自动启动和异常恢复流程；
* AUTO Failover、Fallback Recovery 和 Priority Recovery 控制循环；
* Runtime State 中与 AUTO 相关的状态维护及并发控制；
* Settings 在线生效、延迟生效和需要停止后生效的实现方式；
* 检测 URL、检测超时和检测并发等 Settings 与健康检测模块的映射；
* API 的状态校验、错误码和操作可用性；
* 人工单 Node 和批量健康检测的 API 及页面交互；
* 页面中的运行状态、Current Node、Default Node、Node 健康状态、priority 及级联预览展示。

## 7.1 DIRECT、Outbound 与 Route 页面展示

设计时需要明确：

* DIRECT 是否在 Outbound 页面展示，以及桌面和移动页面中的展示位置、只读样式和操作入口；
* 创建或修改 Route 时，DIRECT 与已有 MANUAL/AUTO 的目标选择方式，以及已有 Route 目标的展示；
* 用户创建和编辑 Outbound 时，仅提供 MANUAL/AUTO 类型，并沿用已有类型转换规则；
* DIRECT 的字段显隐，不展示其不具备的 Node、Current Node 或健康状态；
* DIRECT 系统标识在页面和内部 API 中的表达，以及 Route 保存 DIRECT 目标选择的方式。

展示方案遵循第 2、5、7 章的业务规则：DIRECT 为系统内置、全局唯一的只读 Outbound，不保存独立数据库记录；Route 仍需持久化其目标选择。
