# TODO：前 7 章修改后的后续需求同步

第 1～7 章已完成需求模型及 sing-box 配置管理职责重构。后续需求章节应以前 7 章为基线同步检查和调整，避免重复定义已有业务规则，并确保运行管理、AUTO、Settings、API 和页面行为与前 7 章保持一致。

## 1. Running / 生命周期管理

检查运行管理相关需求，明确：

- Start、Restart、自动启动和异常恢复等所有实际启动 sing-box 的场景均遵循 REQ-CONFIG-002～003；
- 人工 Start 失败、Restart 失败和异常恢复失败时的管理状态转换；
- 管理状态 `running` 与 sing-box 实际进程状态的区别；
- `running` 状态下即使 sing-box 实际进程退出，配置修改限制仍遵循 REQ-CONFIG-012；
- Stop 后进入 `stopped` 状态，才允许执行 REQ-CONFIG-010 所述业务数据修改；
- 每次启动成功后的 Runtime State 初始化与 REQ-CONFIG-004 保持一致。

第 5 章只定义配置生成、校验和启动前提，不负责定义生命周期及启动失败后的管理状态转换。

## 2. AUTO 自动管理

检查 AUTO 相关需求，明确：

- 只有 Routed AUTO 执行自动管理；
- Failover 的触发条件、节点选择和切换规则；
- Fallback Recovery 的触发条件和恢复规则；
- Candidate Priority Recovery 的触发条件和择优规则；
- 每次 Candidate 选择和 Priority Recovery 使用最新 Node Pool priority；
- priority 在线修改本身不立即触发 AUTO 节点切换；
- AUTO Runtime State、节点健康状态和失败计数的管理规则；
- AUTO Current Node 不作为下一次启动的恢复依据。

Candidate Node、Fallback Node、Default Node、Current Node 和 Node Pool priority 的定义沿用前 7 章，不重复定义；相关行为与 REQ-CONFIG-004、REQ-CONFIG-005 和 REQ-CONFIG-009 保持一致。

## 3. Settings

Settings 与第 5 章定义的 sing-box 业务配置管理分离。

检查 Settings 相关需求，明确：

- 哪些 Settings 支持 `running` 状态在线修改；
- 哪些 Settings 修改需要 `stopped`；
- Settings 的保存和生效规则；
- 在线修改 Settings 是否影响 Current Node、Default Node 或 AUTO Runtime State；
- 需要重新启动相关组件才能生效的 Settings，其保存和生效规则。

不得将 Settings 纳入 REQ-CONFIG-010 中 Subscription、Node、Inbound、Outbound、Route 的业务数据范围。

## 4. API / 页面行为

检查 API 和页面相关需求，明确：

- Node Pool 按 priority 的展示顺序；
- priority 的查询和修改接口；
- MANUAL Current Node 与 Default Node 的展示关系；
- `running` / `stopped` 状态下各操作的可用性；
- Current Node 不可获取时的页面和 API 表达；
- 禁止操作时的返回结果和错误提示；
- Subscription Sync、Subscription 删除及其他级联修改的预览、确认和取消交互。

API 和页面行为不得重新定义或改变前 7 章已经确定的业务规则。

## 5. 全文一致性检查

后续章节修改完成后统一检查：

- `Default Node`：数据库持久化的默认节点；
- `Current Node`：MANUAL/AUTO 当前实际生效的运行时节点；
- `Fallback Node`：AUTO 的 Default Node；
- `Candidate Node`：AUTO Node Pool 中除 Fallback Node 外参与自动选择的节点；
- `Node Pool priority`：Node 在具体 MANUAL/AUTO Node Pool 中的优先级，不得描述为 Node 的全局 priority；
- `running` / `stopped`：ProxyHub 管理状态，不等同于 sing-box 实际进程是否存在；
- 删除与前 1～7 章重复定义的业务规则；
- 检查全部 REQ-CONFIG 交叉引用，并统一为当前 REQ-CONFIG-001～REQ-CONFIG-021。
