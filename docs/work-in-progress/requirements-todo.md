# TODO：第 1～9 章修改后的后续需求同步

第 1～9 章已完成业务模型、sing-box 配置管理、运行控制及 Node 健康检测职责重构。后续章节应以前 1～9 章为基线同步检查和调整，避免重复定义已有业务规则，并确保 AUTO、Settings、API 和页面行为保持一致。

---

## 1. AUTO 自动管理

整理第 10 章时检查：

* 只有 Routed AUTO 执行自动管理；
* Current Node 为 Candidate 时的检测和连续失败计数规则；
* Failover 的触发条件及切换到 Fallback 的规则；
* Fallback Recovery 的触发条件、Candidate 检测和节点选择规则；
* Candidate Priority Recovery 的触发条件、检测范围和择优规则；
* 每次 Candidate 选择和 Priority Recovery 使用当前 Node Pool priority；
* priority 在线修改本身不立即触发 AUTO 节点切换；
* Fallback 持续时间的计算和超时处理；
* AUTO 在什么条件下需要重启 sing-box；
* AUTO 节点切换失败后的处理规则；
* AUTO 导致 sing-box 重启失败时，管理状态及后续恢复行为；
* AUTO Current Node、连续失败次数及相关计时在运行周期中的变化规则；
* AUTO 使用第 9 章定义的 Node 检测流程和检测结果，不重复定义健康检测逻辑。

Candidate Node、Fallback Node、Default Node、Current Node、Node Pool priority、Runtime State 和 Node 健康检测的基础定义沿用前 1～9 章，不重复定义。

sing-box 每次成功启动或重启后均自然开始新的运行周期。第 10 章只定义 AUTO 为什么以及何时触发切换或重启，不重复定义运行周期初始化规则。

---

## 2. Settings

Settings 与 sing-box 业务配置管理及 Runtime State 分离。

整理 Settings 相关需求时检查：

* 哪些 Settings 支持 `running` 状态在线修改；
* 哪些 Settings 修改需要 `stopped`；
* Settings 的保存和生效规则；
* 在线修改检测相关 Settings 后，新检测使用何时生效的参数；
* 在线修改 AUTO 相关 Settings 后，后续 AUTO 控制何时使用新参数；
* Settings 修改是否影响 Current Node、Default Node 或 Runtime State 中与 AUTO 相关的状态；
* 需要重新启动 ProxyHub 或其他组件才能生效的 Settings，其保存和生效规则；
* 健康检测相关 Settings 的配置项、默认值、生效时机和修改限制；
* 检测并发配置与第 9 章批量检测规则保持一致；
* 控制周期相关配置与第 8 章后台控制循环保持一致。

Settings 不属于 Subscription、Node、Inbound、Outbound、Route 等 sing-box 业务配置数据。

---

## 3. API / 页面行为

整理 API 和页面相关需求时检查：

* Node Pool 按 priority 的展示顺序；
* priority 的查询和修改接口；
* MANUAL Current Node 与 Default Node 的展示关系；
* AUTO Current Node、Fallback Node 和 Candidate Node 的展示关系；
* Node 健康状态及检测信息的页面/API 展示；
* 人工检测中的单 Node 和批量检测入口；
* 检测执行中的页面状态展示；
* `running` / `stopped` 状态下各操作的可用性；
* 管理状态与 sing-box 实际进程状态分别展示；
* Current Node 或实际进程状态不可获取时的页面和 API 表达；
* 禁止操作时的返回结果和错误提示；
* Subscription Sync、Subscription 删除及其他级联修改的预览、确认和取消交互；
* Start、Stop、Restart 的页面/API 结果与第 8 章运行控制规则保持一致。

API 和页面只表现已有业务规则，不重新定义或改变前面章节的业务逻辑。

---

## 4. 全文一致性检查

后续章节修改完成后统一检查：

* `Default Node`：数据库持久化的默认节点；
* `Current Node`：MANUAL/AUTO 当前运行周期中实际生效的运行时节点；
* `Fallback Node`：AUTO 的 Default Node；
* `Candidate Node`：AUTO Node Pool 中除 Fallback Node 外参与自动选择的节点；
* `Node Pool priority`：Node 在具体 MANUAL/AUTO Node Pool 中的优先级，不描述为 Node 的全局 priority；
* `Runtime State`：当前 sing-box 运行周期中的临时运行状态，不跨运行周期保留，不作为数据库持久化业务数据；
* `running` / `stopped`：ProxyHub 对 sing-box 的运行管理状态，不等同于 sing-box 实际进程状态；
* Routed AUTO 的定义和使用保持一致；
* Node 健康检测统一遵循第 9 章定义，不在其他章节重复定义；
* 删除后续章节中对前 1～9 章已有业务规则的重复定义；
* 删除已经失效的具体 REQ 编号引用；
* 能直接描述行为时直接描述，避免通过具体 REQ 编号跳转；
* 必须跨章节引用时优先引用章节或概念，而不是具体 REQ 编号；
* 检查第 10～14 章中遗留的旧运行模型、旧配置模型和失效交叉引用。

---

## 5. 本轮从第 8 章移出的内容

以下内容已由对应章节处理：

* 批量 Node 检测的并发规则 → 第 9 章；
* AUTO 检测与人工检测之间的并发关系 → 第 9 章；
* 同一 Node 并发检测的结果更新规则 → 第 9 章；
* AUTO 触发 sing-box 重启的具体条件 → 第 10 章；
* Fallback 超时后的 Restart 行为 → 第 10 章；
* AUTO 节点切换失败是否需要 Restart 以及失败后的处理 → 第 10 章。

以下内容已从正式需求中删除，不需要迁移到其他章节：

* “不执行全局 Node 周期扫描”等反向需求描述；
* 任务队列、worker、独立调度器等未采用实现方案的说明；
* 严格 FIFO、公平锁等锁实现细节；
* 请求取消、合并、去重、排队等未要求的机制；
* crash counter、指数退避、cooldown 等未要求的恢复机制；
* 系统级检测总并发上限等未定义需求；
* “V1 / 第一版暂不实现 / 后续考虑”等版本规划式说明。
