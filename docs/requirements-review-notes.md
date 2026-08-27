# ProxyHub 个人版第一版需求评审待修改项

本文记录评审过程中已确认、但计划后续统一写入 `docs/01-requirements.md` 的修改项。本文不是正式需求依据。

## 待修改

### Subscription 运行状态限制

- 统一在 `7.1 运行期间允许的修改` 中描述，不在 `5. 订阅管理` 重复规定。
- 补全 `REQ-CONFIG-001`：sing-box running 时，除禁止刷新 Subscription 外，还应明确禁止新增、修改和删除 Subscription。
- 后续修改时检查 `3.5 订阅刷新`、`3.6 人工修改配置` 与 `REQ-CONFIG-001` 的表述一致性。

### Manual Outbound Node 顺序（替代优先级与排序）

- Manual Outbound 的 Node 不定义优先级，第一版不提供人工排序；只保存稳定的节点加入顺序，新加入的 Node 追加到末尾。
- 稳定加入顺序用于生成 selector 的 `outbounds` 和确定 Current Node 被删除后的回退节点，不参与健康判断、自动故障切换或自动选择。
- 新建 Manual Outbound 时至少选择一个 Node，第一个加入的 Node 成为初始 Current Node，并作为 selector 的 `default`。
- Manual Outbound 人工切换成功后只更新持久化的 Current Node，不改变 Node 顺序；后续重新生成配置时以持久化的 Current Node 作为 `default`。
- Candidate 优先级只属于 Auto Outbound。Manual Outbound 转为 Auto Outbound 时，在转换页面确认 Candidate 优先级，无需提前为 Manual Node 引入优先级或排序能力。
- 删除原“Manual Node 具有连续、唯一的 1 至 N 优先级并支持人工排序”方案，以本文件后续重写的第 6 章为准。

### `6. Inbound、Outbound 与 Route` 整章重写

- 将本章按“Inbound、Outbound 通用约束、三种 Outbound、Manual/Auto 转换、Route 与级联”重新组织。
- 本章定义业务对象、节点池和转换规则；selector 的完整生成细节后续还需同步到 `7.2 配置生成`。
- 建议使用以下内容整体替换当前第 6 章。

#### 6.1 Inbound

**REQ-INBOUND-001** 系统允许创建任意数量的 Inbound，支持 HTTP、SOCKS、Mixed、Shadowsocks 和 VMess。

**REQ-INBOUND-002** 每个 Inbound 独立定义名称、监听协议、监听地址、监听端口和该协议所需的认证参数。Mixed 在同一端口兼容 HTTP 和 SOCKS。

**REQ-INBOUND-003** 未绑定 Route 的 Inbound 只保存于数据库，不写入 sing-box 配置，也不对外监听。

#### 6.2 Outbound 通用约束

**REQ-OUTBOUND-001** Outbound 分为 Manual Outbound、Auto Outbound 和 Direct Outbound。Manual Outbound 与 Auto Outbound 使用 Node 并映射为 sing-box selector；Direct Outbound 不使用 Node，映射为 sing-box direct outbound。

**REQ-OUTBOUND-002** Node 是全局对象，可以被多个 Manual Outbound 或 Auto Outbound 复用，但在同一个 Outbound 的 Node Pool 中只能出现一次。

**REQ-OUTBOUND-003** Manual Outbound 和 Auto Outbound 的 selector 必须包含其 Node Pool 中的全部 Node。selector 发生选择切换时必须中断仍绑定旧节点的已有入站连接；具体配置字段在 `7.2 配置生成` 中统一规定。

#### 6.3 Direct Outbound

**REQ-OUTBOUND-004** Direct Outbound 不包含 Node，不存在 Current Node，不执行节点检测或自动故障切换，流量直接访问目标地址。

#### 6.4 Manual Outbound

**REQ-OUTBOUND-005** Manual Outbound 至少包含一个 Node，不定义 Node 优先级，不执行自动故障切换。新建普通 Outbound 时默认类型为 Manual Outbound。

**REQ-OUTBOUND-006** Manual Outbound 保存稳定的 Node 加入顺序，第一版不提供人工排序。新加入的 Node 追加到末尾；删除 Node 后其余 Node 保持原有相对顺序。

**REQ-OUTBOUND-007** 新建 Manual Outbound 时，第一个加入的 Node 成为初始 Current Node。生成 selector 时，`outbounds` 按稳定加入顺序包含全部 Manual Node，`default` 设置为持久化的 Current Node。

**REQ-OUTBOUND-008** 用户可以在 sing-box running 时人工切换 Manual Outbound 的 Current Node。只有 Clash API 明确确认切换成功后，系统才持久化新的 Current Node；切换失败时保留原 selector 选择和数据库选择，并在页面提示失败。人工切换不改变 Node 顺序。

**REQ-OUTBOUND-009** Manual Outbound 的 Current Node 被移出但 Node Pool 仍非空时，自动以剩余 Node 中最早加入者作为新的持久化 Current Node；失去全部 Node 时按 `6.8 Route 与级联删除` 删除该 Outbound。

#### 6.5 Auto Outbound

**REQ-OUTBOUND-010** Auto Outbound 至少包含两个不同 Node，其中必须有且只有一个 Fallback Node，并至少有一个 Candidate Node。同一 Node 不能同时承担 Fallback 和 Candidate 角色。

**REQ-OUTBOUND-011** Candidate Node 由用户手工排序。保存后系统生成连续、唯一的 1 至 N 优先级；系统不根据 delay、健康状态或其他指标自动调整该优先级。Fallback Node 不参与 Candidate 排序。

**REQ-OUTBOUND-012** 生成 Auto Outbound selector 时，`outbounds` 第一项固定为 Fallback Node，后续包含按人工优先级排列的全部 Candidate Node；`default` 固定为 Fallback Node。Fallback 排在第一项不表示其属于 Candidate。

**REQ-OUTBOUND-013** Auto Outbound 的 Current Node 完全由后台控制循环管理，用户不能临时人工切换或锁定 Current Node。Auto Outbound 每次实际启动或重启后从 Fallback Node 初始化；`default` 只定义启动初始选择，不提供自动故障切换能力。

**REQ-OUTBOUND-014** 未被 Route 引用的 Auto Outbound selector 仍写入 sing-box 配置，但不运行自动检测、故障切换、Fallback Recovery、Candidate Priority Recovery 或 Fallback 超时重启控制。未被 Route 引用的 Manual Outbound selector 同样写入配置。

#### 6.6 Manual Outbound 转为 Auto Outbound

**REQ-OUTBOUND-015** 只有 sing-box stopped 时才能转换 Outbound 类型。Manual Outbound 转为 Auto Outbound 前，其现有 Node Pool 必须至少包含两个 Node；不允许在转换过程中从 Node Pool 外另选 Fallback Node，也不允许因转换增加或丢弃 Node。

**REQ-OUTBOUND-016** 用户必须从原 Manual Node Pool 中选择一个 Node 作为 Fallback Node，其余 Node 全部成为 Candidate Node，并在保存转换前确认 Candidate 优先级。原 Manual Current Node 在转换后不保留特殊角色，除非它被选为 Fallback Node。

**REQ-OUTBOUND-017** 转换完成后，selector 的 `outbounds` 调整为 Fallback Node 在前、Candidate Node 按确认后的优先级排列，`default` 设置为 Fallback Node。Auto Outbound 下次启动时从 Fallback Node 初始化。

#### 6.7 Auto Outbound 转为 Manual Outbound

**REQ-OUTBOUND-018** Auto Outbound 转为 Manual Outbound 时，保留原 Fallback Node 和全部 Candidate Node，不允许因转换增加或丢弃 Node。转换后的稳定 Node 顺序为原 Fallback Node 在前，原 Candidate Node 按原优先级顺序在后。

**REQ-OUTBOUND-019** 原 Fallback Node 自动成为转换后 Manual Outbound 的持久化 Current Node；原 Candidate 优先级被移除，不再具有业务含义。用户无需在转换时重新选择 Current Node。

**REQ-OUTBOUND-020** 按 `REQ-OUTBOUND-018` 和 `REQ-OUTBOUND-019` 转换时，sing-box selector 的 `outbounds`、`default` 和中断旧连接设置均不需要改变；系统只转换 ProxyHub 中的 Outbound 类型、节点角色和持久化 Current Node，并清除该 Auto Outbound 的临时控制状态。

#### 6.8 Route 与级联删除

**REQ-ROUTE-001** Route 只表达一个 Inbound 到一个 Outbound 的映射，不提供规则分流或额外“服务”业务层。每条 Route 必须同时引用一个 Inbound 和一个 Outbound。

**REQ-ROUTE-002** 一个 Inbound 最多被一条 Route 引用；一个 Outbound 可以被零条、一条或多条 Route 引用。多条 Route 引用同一个 Outbound 时，共享该 Outbound 的 Node Pool、Current Node 和运行状态。

**REQ-ROUTE-003** 删除 Inbound 或 Outbound 时，一并删除引用它的 Route。

**REQ-ROUTE-004** 删除 Node 后，从所有 Outbound Node Pool 中删除该 Node 的引用，并按以下规则继续处理：

- Manual Outbound 仍有 Node：按 `REQ-OUTBOUND-009` 保留或重新确定 Current Node；
- Manual Outbound 失去全部 Node：删除该 Outbound；
- Auto Outbound 失去 Fallback Node：删除该 Outbound；
- Auto Outbound 失去全部 Candidate Node：删除该 Outbound；
- Auto Outbound 只删除部分 Candidate Node：保留其余 Candidate 的相对顺序，并重新整理为连续的 1 至 N 优先级；
- 删除 Outbound 后，继续删除引用它的全部 Route。

**REQ-ROUTE-005** 人工删除 Node、删除 Subscription 和订阅刷新删除 Node 都使用相同的级联规则，并在执行前向用户展示完整影响；用户确认后在同一个业务事务中完成 Node、Outbound 和 Route 的变更。

#### 后续同步检查

- 同步更新 `2.1 核心关系`、`2.2 名词` 和 `2.3 全局不变量`，避免 Node Pool、Current Node 和 Route 基数关系重复或冲突。
- 同步更新 `7.1 运行期间允许的修改`，继续保持 Outbound 类型转换只能在 sing-box stopped 时执行。
- 同步更新 `7.2 配置生成`：Manual selector 的 `default` 为持久化 Current Node；Auto selector 的 `outbounds` 包含 Fallback 和全部 Candidate，且 `default` 为 Fallback；两类 selector 均启用切换时中断已有入站连接。
- 同步检查 `8.2 启停与重启`：Manual 恢复持久化 Current Node，Auto 从 Fallback 初始化。
- 如果启用 sing-box cache file，必须避免缓存的 selector 历史选择覆盖上述 Manual `default` 或 Auto Fallback 初始化规则；具体方案留待 sing-box 集成设计确定。
