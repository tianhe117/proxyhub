# ProxyHub V1.0 设计 TODO

以已冻结的 `docs/01-requirements.md` 为依据。本文只记录仍需确定的数据结构、实现方式、页面与内部 API 契约及验证样例；设计结论不得改变需求规定的产品行为。

## 1. 业务数据与约束

### 1.1 数据模型和 Node Pool

- 设计 Subscription、Node、Inbound、MANUAL/AUTO、Node Pool 和 Route 的表、标识及关联约束；为不入库的 DIRECT 设计稳定的系统标识和 Route 目标表达。
- 设计 Subscription Node 的来源与名称身份匹配字段，并限制其写入入口；区分从 Node Pool 移除成员与删除全局 Node。
- 设计 Node Pool priority 的唯一性约束、初始分配、插入、删除和重新排序算法；允许不连续并避免无谓整体重编号，在线批量调整时避免中间状态违反唯一约束，并使后续 AUTO 选择读取最新值。
- 设计 Default Node 必须属于 Node Pool、同一 Node Pool 不重复包含 Node、一个 Inbound 最多被一条 Route 引用等约束的数据库与业务层校验位置。

### 1.2 级联修改与事务

- 设计多 Node 删除后的最终 Node Pool 计算方式，以及 Default Node 替换、MANUAL/AUTO 和 Route 级联删除的共同处理入口。
- 设计普通删除、Subscription Sync 和 Subscription 删除共用的级联影响预览结构与确认后的数据库事务边界。
- 设计预览中的新增、修改、删除、跳过及级联影响字段；失败时保证一次业务变更整体回滚。

### 1.3 Inbound 监听冲突

- 设计监听地址和端口的冲突判定，覆盖通配地址、具体 IPv4/IPv6 地址及 ProxyHub Web 监听地址。
- 确定保存时校验的位置和冲突错误的内部 API 表达。

## 2. sing-box 配置与运行控制

### 2.1 配置生成

- 设计 Node、selector、Inbound、Route 和 DIRECT 的 sing-box 字段映射、tag 命名及引用关系；为 selector 成员列表确定不依赖数据库 priority 的稳定顺序。
- 设计启动时从 Default Node 设置 selector 初始选择的方式，以及 sing-box cache file 的使用策略，确保上一运行周期的选择不会覆盖本次初始化。
- 设计临时配置生成、`sing-box check`、正式配置替换和进程启动的执行顺序，以及最近一次成功运行配置的保存位置和更新时机。
- 准备可检查的配置样例：仅 DIRECT、MANUAL、AUTO、多 Route 共享 Outbound、未引用 Outbound，以及多 Inbound 混合 Route。

### 2.2 生命周期与控制循环

- 设计 ProxyHub 启动时的自动启动、人工 Start/Stop/Restart、意外退出恢复和 AUTO 触发重启的流程，并区分管理状态与实际进程状态。
- 设计运行控制锁的边界与操作顺序，覆盖后台控制周期、配置写入、priority 调整、MANUAL 切换及二进制替换；保持 Settings 保存和人工检测的既定并发规则。
- 设计成功启动后的 Runtime State 初始化、进程退出后的状态表达，以及单个控制周期结束后才等待 Control Interval 的调度实现。

### 2.3 Current Node 查询与切换

- 确定 sing-box 控制接口的配置、Current Node 查询、切换调用和成功判定方式。
- 设计已被 Route 引用的 MANUAL 的切换前提、目标 Node 校验、运行时 Current Node 与数据库 Default Node 的更新顺序及异常处理。
- 为未被 Route 引用的 MANUAL 设计仅更新 Default Node 的操作路径，不调用 sing-box，也不生成运行中的 Current Node。
- 设计查询结果与本地 Runtime State 不一致时的处理，以及切换后中断旧 Node 连接的实现和多 Route 共享 Outbound 的验证样例。

### 2.4 AUTO 控制实现

- 设计每个 Routed AUTO 的运行时状态结构、单调时钟计时、连续失败计数及控制周期内的处理顺序。
- 设计 Candidate 检测批次、当前 priority 读取、Fallback/Priority Recovery 切换调用与失败处理的代码边界。
- 设计 AUTO 重启 sing-box 时结束本控制周期、初始化新运行周期及后续进程守护衔接的实现。

## 3. Node 与 Subscription 输入

### 3.1 Node 协议和分享 URI

- 确定受支持 sing-box 版本下 VMess、VLESS、Trojan、Shadowsocks 和 Hysteria2 的字段映射、合法参数组合与校验规则。
- 确定 Reality、uTLS、WebSocket、gRPC、HTTP/2 等能力适用的协议及字段组合；明确 sing-box 原生 Shadowsocks plugin 的范围与映射。
- 设计单条分享 URI 的识别、解析、表单回填和错误表达，并准备各协议的有效及无效样例。

### 3.2 Subscription 请求和解析

- 使用实际订阅数据确定首版支持的内容格式、识别和解析流程，并保存可验证的支持与不支持样例。
- 确定 Clash 兼容 User-Agent、HTTPS 请求参数，以及 Sync 与 Refresh 共用或独立的请求处理。
- 设计 Refresh 元信息的提取、请求及 parser 错误分类，以及 Filter/Exclude、Node 校验、重复名称检查和差异计算的处理顺序。
- 确保名称身份匹配不会自动修剪、改写或归一化，并准备同名、改名、无效节点和过滤为空的样例。

## 4. Node 健康检测

- 设计 TCP 检测的连接目标、超时、延迟计算和错误分类；设计通过指定 Node 访问 HTTPS Test URL 的实现与响应延迟计算。
- 设计单次检测结果和内存健康状态的字段，包括 TCP/URL 结果、时间、失败原因与两种延迟；检测完成后一次性更新。
- 设计 AUTO 与人工检测各自的批量并发限制、多个检测请求并发及同一 Node 按完成顺序写回结果的实现。
- 设计 AUTO 控制直接消费本次检测结果、人工检测仅更新展示状态的模块边界；处理检测期间 Node 被删除或 sing-box 不可用的结果。

## 5. Settings 与认证

- 设计 Settings 文件格式、默认值补全、完整校验、原子保存及启动失败时的错误输出；逐项确定合法取值范围。
- 为每个 Setting 标明管理修改方式和生效时机，区分认证设置、运行周期所需参数及只能通过文件修改的 Web 监听设置。
- 设计 Start 读取已成功保存设置的快照，以及 Settings 保存与 Start 并发、检测或控制周期读取参数时的处理。
- 设计密码哈希、认证密钥存储、会话失效、登录/退出及页面、内部 API、日志下载的认证保护。

## 6. 内部 API 与页面

- 设计实体管理、运行控制、Subscription Sync/Refresh、人工检测、MANUAL 节点选择、priority 调整和 sing-box 管理的内部 API 请求与响应结构。
- 为管理状态或实际进程状态不满足条件的操作设计一致的错误返回和页面提示；设计 Start/Stop/Restart 与配置检查失败的结果展示。
- 设计 Node Pool 的 priority 顺序和调整交互，以及 MANUAL Current/Default、AUTO Current/Fallback/Candidate 的区分展示；未引用 Outbound 不显示运行中的 Current Node。
- 设计 Node 健康状态、TCP/URL 检测信息、单个或批量人工检测进行中状态的页面与 API 表达。
- 区分管理状态、实际进程状态、未运行、未被 Route 引用和运行信息查询失败等页面/API 状态。
- 设计级联影响预览、确认及取消交互；设计桌面和移动页面各自的展示及操作入口。
- 确定 DIRECT 是否在 Outbound 页面展示、在 Route 目标选择中的只读表现，以及内部 API 的系统标识表达。

## 7. 日志、安全信息与部署

- 设计关键事件记录、近期事件展示、日志文件下载及日志文件管理方式。
- 设计凭据、分享 URI、完整 Subscription URL、parser 原始输入和底层错误的统一脱敏位置，并准备日志、错误提示和差异预览样例。
- 确定 sing-box 远程版本来源、amd64 资产选择、完整性、可执行性和版本信息验证、正式二进制替换及失败保护的实现。
- 设计 Docker Compose 与 Ubuntu Python/venv 部署中的目录、配置文件及二进制位置，使两种部署使用一致的配置格式。
