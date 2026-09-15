# ProxyHub 设计 TODO

本文记录需求确认后需要在模块设计阶段明确的实现事项。本文不是正式需求依据，设计结论不得改变 `docs/01-requirements.md` 规定的产品行为。

## 1. sing-box 模块设计

### 1.1 Outbound、Route 与 sing-box 配置映射

设计时需要明确并形成可验证样例：

- 全局 Node 到 sing-box 独立 Outbound 的字段映射、tag 生成和唯一性规则；
- 被 Route 引用的 MANUAL/AUTO 到 sing-box selector 的映射，以及未被 Route 引用的 MANUAL/AUTO 不生成对应运行对象的处理；
- Node Pool 到 selector 节点列表的映射及顺序规则；
- AUTO 择优使用数据库最新 priority，而不依赖 selector 自身顺序的实现方式；
- MANUAL/AUTO 的 Default Node 到启动时 Current Node 初始选择的映射；
- AUTO 将 Default Node 作为 Fallback Node 的实现方式；
- DIRECT 对应的系统内置 direct Outbound、保留 tag 及 Route 到该 tag 的映射；
- Inbound、Route、selector、Node 独立 Outbound 和 DIRECT tag 的完整引用关系；
- sing-box cache file 是否启用，以及如何保证缓存状态不会恢复上一运行周期的 Current Node或覆盖 Default Node 初始化规则；
- 配置生成、`sing-box check`、正式配置原子替换和 sing-box 启动之间的执行顺序；
- 最新成功运行配置的保留位置、更新时机及故障排查使用方式。

需要至少覆盖以下配置样例：

- 仅 DIRECT Route；
- MANUAL Route；
- AUTO Route；
- 多条 Route 共享同一个 MANUAL/AUTO；
- 未被 Route 引用的 MANUAL/AUTO；
- 多个 Inbound 和 Route 混合使用。

### 1.2 Current Node 运行时控制

设计时需要明确：

- MANUAL 在线切换时对目标 Node 属于对应 Node Pool 的校验位置；
- sing-box Current Node 查询、切换及切换成功确认的调用方式；
- sing-box 控制能力不可用或切换失败时的错误处理；
- 切换成功后 Runtime Current Node 与数据库 Default Node 的一致性处理；
- Current Node 切换后已有连接是否以及如何中断，使后续连接使用新的 Current Node；
- Current Node 查询结果与本地 Runtime State 不一致时的处理方式。

### 1.3 priority 在线修改

设计时需要明确：

- Node Pool priority 的持久化结构和唯一性约束；
- 新建 Node Pool 时初始 priority 的生成方式；
- 插入、删除和重新排序时 priority 的分配策略；
- 在允许 priority 不连续的前提下避免无意义整体重编号的策略；
- 在线调整多个 priority 时避免中间状态违反唯一约束的更新方式；
- priority 修改与 AUTO 后台控制循环并发时，保证后续节点选择读取最新 priority 的方式。

具体 priority 数值分配算法属于设计实现，不写入正式需求。

## 2. Subscription 设计

### 2.1 Subscription 请求与解析

设计时需要明确：

- Clash 兼容 User-Agent 的具体值及请求头组织方式；
- Subscription Refresh 所需流量、总流量、到期时间等元信息的获取和解析方式；
- Subscription Sync 与 Refresh 共用和独立的请求处理逻辑；
- Subscription URL 请求错误、格式错误和 parser 错误的内部分类及对外表达；
- Filter/Exclude、Node 校验和差异计算的处理顺序；
- Subscription Node `name` 身份匹配规则的具体实现，确保不会发生自动修剪、改写或 Unicode 归一化。

### 2.2 差异预览与事务

设计时需要明确：

- Subscription Sync 差异预览的数据结构；
- 新增、修改、删除和跳过 Node 的预览数据组织方式；
- Node 删除产生的 Default Node 替换、MANUAL/AUTO 删除和 Route 删除的级联影响计算方式；
- 用户确认前后数据发生变化时的一致性处理策略；
- 用户确认后的事务边界及失败回滚方式；
- Subscription 删除与 Subscription Sync 共用级联处理逻辑的方式。

## 3. 业务数据与级联处理

设计时需要明确：

- 一次删除多个 Node 时，先计算全部目标 Node 删除后的最终 Node Pool，再统一执行 Default Node 替换和 MANUAL/AUTO 删除的实现方式；
- Default Node 被删除后选择最小 priority Node 的实现方式；
- MANUAL/AUTO 删除后级联删除全部引用 Route 的处理方式；
- Node、Inbound、MANUAL/AUTO 删除产生级联影响时的预览和确认数据结构；
- 多对象级联修改整体成功或整体不生效的事务实现；
- Node Pool 正常编辑与全局 Node 删除导致 Node Pool 缩减两种场景的处理边界。

### 3.1 Inbound 监听冲突

设计时需要明确：

- Inbound 监听地址和端口冲突的判断方式；
- `0.0.0.0`、`127.0.0.1`、具体网卡地址及 IPv6 地址之间的冲突判断；
- Inbound 与 ProxyHub 自身监听端口的冲突检查范围；
- 冲突检查的执行位置和错误返回方式。

## 4. Node 协议与输入映射

设计时需要明确并形成可验证样例：

- VMess、VLESS、Trojan、Shadowsocks 和 Hysteria2 的字段映射、合法组合及版本兼容范围；
- Reality、uTLS fingerprint、WebSocket、gRPC 和 HTTP/2 等能力适用的协议、字段组合和校验规则；
- 当前集成 sing-box 可直接处理的 Shadowsocks plugin 范围、字段映射和校验方式，以及不安装或管理额外插件程序的实现边界；
- 单条分享 URI 的解析、字段回填和错误处理；
- Node 必要字段、端口和协议参数的保存校验规则。

## 5. 敏感信息处理

设计时需要明确：

- Node 凭据、分享 URI、完整 Subscription URL 和 parser 原始输入等敏感信息的识别范围；
- 日志、错误信息和差异预览的统一脱敏位置及处理方式；
- 差异预览允许展示的安全字段和失败原因；
- HTTP、parser 和 sing-box 底层错误向用户展示或写入日志前的清理规则；
- 对脱敏规则形成可验证样例和测试用例。

## 6. 后续章节设计同步

Running、AUTO、Settings 和 API/Page 需求冻结后，再补充对应模块设计，重点包括：

- ProxyHub 管理状态机与 sing-box 进程生命周期；
- Start、Stop、Restart、自动启动和异常恢复流程；
- AUTO Failover、Fallback Recovery 和 Priority Recovery 控制循环；
- AUTO Runtime State 的维护与并发控制；
- Settings 在线生效、延迟生效和需要停止后生效的实现方式；
- API 的状态校验、错误码和操作可用性；
- 页面中的运行状态、Current Node、Default Node、priority 及级联预览展示。
