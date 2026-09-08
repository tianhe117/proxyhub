# TODO：第 5 章重构后的需求同步修改

第 5 章已重构为“sing-box 配置管理”，后续章节需要按照新的职责边界同步检查和调整，避免重复定义或遗漏原有需求。

## 1. Subscription

检查 Subscription 相关需求，明确：

- Subscription 新增、修改、删除和 Sync 必须遵循 REQ-CONFIG-010，仅允许在 `stopped` 状态执行；
- Refresh 可以在 `running` 和 `stopped` 状态执行；
- Refresh 仅更新流量、到期时间等元信息，不修改 Node；
- 修改 Subscription URL、Filter、Exclude 等配置时只保存数据库，不自动执行 Sync；
- Sync 时才根据最新 Subscription 配置更新 Node；
- Sync 的新增、更新、删除 Node、事务处理及关联关系处理由 Subscription 章节定义。

避免在 Subscription 章节重复描述 sing-box 配置生成和启动规则。

## 2. Node / Inbound / Outbound / Route

检查相关业务对象需求，明确：

- Node、Inbound、Outbound、Route 的新增、修改和删除均遵循 REQ-CONFIG-010；
- 新增或修改 Inbound 时检查监听地址和端口是否与已有 Inbound 或 ProxyHub 自身监听端口冲突，存在冲突时禁止保存；
- Node Pool 中 priority 的定义、唯一性、排序规则由 Outbound 章节定义；
- Node Pool 成员调整属于普通配置修改，必须在 `stopped` 状态执行；
- 仅修改 Node Pool priority 属于 REQ-CONFIG-009 规定的在线修改；
- Default Node 必须属于对应 Node Pool；
- Node Pool 成员删除、Default Node 删除等情况下的 Default Node 调整规则由 Outbound 章节定义；
- MANUAL 在线节点切换的可用条件、目标 Node 合法性和连接处理规则由 Outbound 章节定义；
- AUTO 不允许人工修改 Current Node；
- MANUAL/AUTO 类型转换、Route 引用及删除约束由对应章节定义。

避免在这些章节重复描述“启动时重新生成 sing-box 配置”的通用规则。

## 3. Running / 生命周期管理

检查运行管理章节，明确：

- Start、Restart、自动启动和异常恢复等所有实际启动 sing-box 的场景均执行 REQ-CONFIG-002～003；
- 人工 Start 失败、Restart 失败和异常恢复失败时的管理状态分别由运行管理章节定义；
- 管理状态 `running` 与 sing-box 实际进程状态必须明确区分；
- `running` 状态下即使 sing-box 实际进程退出，配置修改限制仍按 REQ-CONFIG-012 执行；
- Stop 后进入 `stopped` 状态，才允许执行 REQ-CONFIG-010 所述业务数据修改；
- 每次启动成功后的 Runtime State 初始化规则与 REQ-CONFIG-004 保持一致。

第 5 章只定义配置能否生成和启动，不负责定义启动失败后的管理状态转换。

## 4. AUTO 自动管理

检查 AUTO 相关需求，明确：

- Candidate Node 和 Fallback Node 的定义；
- Fallback Node 不参与 Candidate Node priority 排序；
- AUTO 每次进行节点选择或 Priority Recovery 时使用数据库中的最新 priority；
- priority 修改本身不立即触发 AUTO 节点切换；
- Fallback Recovery、Priority Recovery、Failover 等自动切换规则由 AUTO 章节定义；
- AUTO Current Node 仅为运行时状态，不作为下一次启动恢复依据。

与 REQ-CONFIG-004、REQ-CONFIG-005、REQ-CONFIG-009 保持一致。

## 5. Settings

Settings 与第 5 章的 sing-box 业务配置管理分离。

检查 Settings 章节并明确：

- 哪些 Settings 支持 `running` 状态在线修改；
- 哪些 Settings 修改需要 `stopped`；
- Settings 的保存和生效规则；
- 在线修改 Settings 是否影响 Current Node、Default Node 或 AUTO Runtime State。

不要将 Settings 纳入 REQ-CONFIG-010 中 Subscription、Node、Inbound、Outbound、Route 的业务数据范围。

## 6. API / 页面行为

在 API 或页面相关需求中补充，不放入第 5 章：

- Node Pool 按 priority 的展示顺序；
- priority 查询和修改接口；
- MANUAL Current Node、Default Node 的展示关系；
- `running` / `stopped` 状态下各操作的可用性；
- 禁止操作时的返回结果和错误提示。

## 7. 术语统一

全文统一以下概念：

- `Default Node`：数据库持久化的默认节点；
- `Current Node`：MANUAL/AUTO 当前实际生效的运行时节点；
- `Fallback Node`：AUTO 的 Default Node；
- `Candidate Node`：AUTO Node Pool 中除 Fallback Node 外参与自动选择的节点；
- `Node Pool priority`：Node 在具体 MANUAL/AUTO Node Pool 中的优先级，不应描述为 Node 的全局 priority；
- `running` / `stopped`：均指 ProxyHub 管理状态，不等同于 sing-box 实际进程是否存在。

完成后检查全文对旧 REQ-CONFIG 编号的交叉引用，并统一更新为新版 REQ-CONFIG-001～REQ-CONFIG-021。
