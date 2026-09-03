# ProxyHub 个人版第一版需求待修改项

本文记录评审过程中已确认、但尚未写入 `docs/01-requirements.md` 的修改项。本文不是正式需求依据；正式需求仍以 `docs/01-requirements.md` 为准。

## 待修改

### 1. 保留 Start、Stop 和 Restart

- 保留 Start、Stop 和 Restart 三个人工控制。
- ProxyHub 分别维护 sing-box 的管理状态 `running` / `stopped` 和实际进程状态；配置修改限制按管理状态判断，页面同时展示实际运行、已退出或启动失败等状态。
- Start 从最新数据库生成完整配置并执行 `sing-box check`；Start 执行期间管理状态仍为 `stopped`，只有检查和进程启动均成功后才进入 `running`，任一步失败都保持 `stopped`。
- Stop 停止 sing-box，并停止进程守护和 AUTO 控制，进入 `stopped`。
- Restart 严格等于在同一次运行控制加锁操作中依次执行 Stop 和 Start：先停止当前 sing-box 并进入 `stopped`，再从最新数据库生成、检查配置并启动；检查或启动失败时保持 `stopped`，不恢复或自动启动旧进程。
- 管理状态为 `running` 但实际进程已退出或恢复失败时，仍禁止结构修改；用户需要先执行 Stop，再修改配置。
- ProxyHub 自身启动时，sing-box 二进制、Settings 和至少一条有效 Route 均存在时仍自动生成、检查并启动 sing-box；手动 Stop 状态不跨 ProxyHub 自身重启持久化。
- sing-box 下载和升级只允许在 `stopped` 时执行，成功后保持 `stopped`，不自动启动。
- 不增加“待应用配置”状态。

### 1.1 stopped 时允许的结构修改

- Subscription 新增、修改、删除和同步订阅节点；
- Node、Inbound 和 Route 的新增、修改和删除；
- MANUAL/AUTO 的新增、删除，以及名称、type、Node Pool、priority、Fallback Node 等结构修改；
- 其他会改变 sing-box 完整配置的业务数据修改。

### 1.2 running 时允许的操作

- 查看状态和日志；
- 刷新 Subscription 的剩余流量、到期时间等信息；
- 人工批量检测 Node；
- 人工切换 MANUAL 的 Current Node；
- 修改允许在线生效的 Settings；
- Stop 和 Restart。

### 2. 启动和重启始终使用最新数据

- Start、人工 Restart 和意外退出后的恢复启动，都从最新数据库重新生成完整配置并执行 `sing-box check`，不直接复用可能过期的正式配置。
- Start 检查失败时记录并显示错误，保持 `stopped`，数据库不回滚。
- Restart 在同一次运行控制加锁操作中先执行 Stop，再执行与 Start 相同的配置生成、检查和启动流程。
- Start 或 Restart 生成的临时配置检查成功后才原子替换正式配置并启动 sing-box。检查失败时保留上一份正式配置供人工排错，但不使用旧配置自动启动；Restart 已停止的旧进程也不恢复。
- MANUAL 运行中切换 Current Node 后，以数据库中的持久化选择为准；下次启动或重启生成配置时自然恢复该 Current Node，不再需要单独定义旧正式配置与数据库选择不一致时的恢复流程。
- AUTO 每次实际启动或重启成功后仍从 Fallback Node 初始化。
- 意外退出后的配置检查或进程启动失败时保持管理状态 `running`，记录错误，并由后续后台周期继续恢复；需要修改配置时，用户先执行 Stop。

### 3. 删除自动全局扫描并允许检测并发

- 删除后台自动全局 Node 周期扫描，以及 `Global Scan` 和 `Global Scan Interval` Settings。
- 保留人工批量检测接口，由用户明确触发；每次可以选择检测全部自建 Node、某一个 Subscription 下的全部 Node，或全部全局 Node。不再建立单独的周期扫描任务。
- AUTO 检测和人工批量检测都只能在管理状态为 `running` 且 sing-box 实际进程正在运行时发起；进程守护未恢复成功时，本周期不执行 AUTO 检测。
- 不再要求 AUTO 检测和人工批量检测在全局范围内互斥，二者允许同时执行。
- 每个 AUTO 检测过程和每个人工批量检测请求分别受 `Max Concurrency` 限制，默认值为 10。第一版不限制用户同时发起的人工批量检测请求数量，也不保证系统级检测总并发上限，由个人用户自行控制。
- 删除“当前已有检测批次时不再启动人工检测”“控制循环等待其他检测批次完成”以及“同一时刻只执行一个检测批次”等限制；不实现检测请求合并、去重或排队。
- Node 展示状态按检测完成顺序更新，后完成的结果覆盖先完成的结果。
- AUTO 只使用其自身控制流程本次取得的检测结果作出判断；人工批量检测不得修改 AUTO 的连续失败次数、Current Node、Fallback 或 Priority Recovery 状态，也不得触发 AUTO 切换。
- 人工批量检测不需要与 Stop 或 Restart 互斥。检测过程中 sing-box 因 Stop、Restart 或意外退出而不可用时，尚未完成的检测允许失败；检测完成时只更新仍然存在的 Node 展示状态和日志，Node 已不存在时丢弃其状态结果。

### 4. Settings 非法值使用常规校验

- 需求只保留“Settings 保存和启动加载前必须通过完整校验，非法值不得应用”的原则。
- 不在需求中逐项定义端口、正整数、超时和取值范围等常规校验规则，具体规则由实现设计确定。

### 5. Settings 在线修改即时生效

- Settings 页面保存时，先校验完整设置，再原子替换 `data/settings.json` 并更新当前进程的内存设置；不启动或重启 sing-box。
- 保存 Settings 不改变 MANUAL/AUTO 的 Current Node，不清空 Node 最近检测信息、AUTO 连续失败次数、Fallback 持续时间或 Priority Recovery 计时，也不主动检测或切换 Node。
- 新设置用于保存后的后续相关处理；已经开始的任务不要求取消、重启或重新计算。
- Username 和 Password 保存后立即生效；Web Listen Address 和 Web Port 仍不能在线修改，只能直接修改 JSON 并在 ProxyHub 重启后生效。
- Node 最近检测信息只用于页面展示和日志；AUTO 仍只使用其自身控制流程当次取得的检测结果作出判断。

### 6. 区分订阅信息刷新与节点同步

- “刷新订阅信息”只更新剩余流量、到期时间等 Subscription 信息，不增加、修改或删除 Node。
- 从订阅重新请求、解析和更新 Node 的操作统一称为“同步订阅节点”，不再称为“刷新订阅”。
- 同步订阅节点仍执行过滤、跳过、差异预览、用户确认、自动替换和级联删除等既有流程。
- 刷新订阅信息不属于配置结构修改，在 `running` 和 `stopped` 时均允许；同步订阅节点属于配置数据修改，只允许在 `stopped` 时执行，完成后由用户执行 Start。
- 全文统一上述两个操作的名称，避免“刷新”同时表示信息更新和 Node 更新。

### 7. priority 只在 stopped 时调整

- Current Candidate 已经是最高 priority Candidate 时，不执行 Priority Recovery。
- MANUAL/AUTO 的 Node priority 属于结构配置，只允许在 `stopped` 时调整，保存后不自动启动 sing-box。
- 下次 Start 时使用新的 priority；AUTO 先以 Fallback Node 作为 Current Node，下一后台控制周期再按新 priority 执行 Fallback Recovery。
- 调整 priority 不改变 MANUAL 的持久化 Current Node 或 AUTO 的 Fallback Node。
- 删除运行中调整 priority 及其生效时间、恢复计时和自动重启等专项规则。

### 8. 统一订阅相关事务范围

- 订阅节点同步、Subscription 删除及其他涉及订阅 Node 的级联操作，统一在一个业务事务中完成 Subscription（适用时）、Node、Outbound 和 Route 的全部相关变更。
- 差异预览只允许用户确认或取消整个结果，不提供逐条选择导入或删除的能力。

### 9. Hysteria2 不单独处理 TCP 检测

- Hysteria2 与其他 Node 使用相同的 TCP + URL 检测流程，不增加协议专用分支。
- Hysteria2 的 TCP 检测允许失败；TCP 结果仍只用于页面展示、日志和排错，不影响最终健康判断或 AUTO 控制。
- Node 的最终健康状态继续只由 URL 检测结果决定。

### 10. Settings 文件异常时终止启动

- `data/settings.json` 不存在时，使用内置默认值创建完整文件；该情况不属于配置异常。
- 文件能够读取并解析为合法 JSON 对象、但缺少部分已定义字段时，使用对应内置默认值补全，再执行完整校验；补全内容只需在内存中生效，不因启动加载自动重写原文件，用户后续从 Settings 页面成功保存时再写入完整设置。
- `data/settings.json` 无法读取、JSON 非法、包含未知结构，或补全缺失字段后仍无法通过完整校验时，记录明确错误并终止 ProxyHub 启动。文件中已经提供但值非法的字段不得用默认值静默替代。
- ProxyHub Web 和 sing-box 均不启动；不使用默认 Settings、临时 Web 地址或修复页面继续运行。
- 保留原 Settings 文件，不自动修改、覆盖或静默回退；错误通过启动输出和正常日志渠道报告，不要求通过管理页面显示。

### 11. 使用单一运行控制锁

- 使用一把进程内运行控制锁，串行化后台控制与 sing-box 生命周期操作，不建立任务队列或复杂调度机制。
- 后台任务从进程守护开始，到全部 Routed AUTO 的检测、判断和切换处理结束，全程持有该锁。
- Start、Stop、Restart、结构配置写操作、MANUAL Current Node 人工切换、sing-box 升级替换以及后台故障恢复重启使用同一把锁。结构配置写操作取得锁后再次确认管理状态为 `stopped`，避免 Start 执行期间修改数据库。
- Restart 在一次持锁期间依次完成 Stop 和 Start，中间不释放运行控制锁，也不允许插入结构配置修改。
- Stop 或 Restart 到来时，如果后台任务正在执行，则等待本次后台任务完整结束后再执行；不取消正在执行的 AUTO 检测。
- `stopped` 状态不运行进程守护或 AUTO 控制；结构配置修改仍需短暂取得运行控制锁并确认状态，但不需要启动或操作 sing-box。
- Settings 保存只原子替换文件和内存设置，不取得运行控制锁，也不启动或重启 sing-box。
- 人工批量检测发起时检查管理状态和实际进程状态，但不持有运行控制锁，可以与后台 AUTO 控制、Stop 或 Restart 并发；进程变化导致的检测失败只更新仍然存在的 Node 展示状态和日志。
- 不额外实现任务取消、运行代次、旧检测结果识别或请求合并；多个生命周期请求同时发生时按取得锁的顺序执行。
