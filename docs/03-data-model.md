# ProxyHub V1.0 数据模型设计

> 文档状态：待审核
> 更新日期：2026-09-18
> 上游文档：[需求规范](01-requirements.md)、[软件架构设计](02-architecture.md)

本文定义业务数据的表、关联、约束，以及 Subscription Sync 和级联删除如何形成一次完整的数据变更。主要对应 REQ-MODEL-001～004、REQ-CONFIG-001～013、REQ-SUB-001～013、REQ-INBOUND-001～003、REQ-OUTBOUND-001～005、REQ-ROUTE-001～004 和 REQ-REL-002～003。Node 协议参数的具体字段与 sing-box 映射由 04 设计确定。

## 1. 表结构

表名和字段名是本设计的实现契约。时间字段采用 UTC Unix 秒；未知元信息使用 `NULL`，不以 `0` 表示未知。协议专用 JSON 的具体键由 04 设计给出。

### 1.1 `subscriptions`

| 字段 | 类型与约束 | 含义 |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Subscription 标识 |
| `name` | `TEXT NOT NULL` | 展示名称 |
| `url` | `TEXT NOT NULL` | 当前订阅地址 |
| `filter_text`、`exclude_text` | `TEXT NOT NULL DEFAULT ''` | 用户输入的筛选词原文 |
| `upload_bytes`、`download_bytes`、`total_bytes` | 非负 `INTEGER NULL` | Refresh 获取的流量元信息 |
| `expires_at`、`refreshed_at` | `INTEGER NULL` | 到期时间、最近成功 Refresh 时间 |

`name` 和 `url` 不设唯一约束；Subscription 可以暂时没有关联 Node。

### 1.2 `nodes`

| 字段 | 类型与约束 | 含义 |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | 全局 Node 标识 |
| `subscription_id` | `INTEGER NULL`，外键指向 `subscriptions.id` | `NULL` 表示自建；非空表示所属 Subscription |
| `name` | `TEXT NOT NULL` | 展示名称；订阅 Node 的身份匹配值 |
| `protocol` | 枚举文本 | `vmess`、`vless`、`trojan`、`shadowsocks`、`hysteria2` |
| `address`、`port` | `TEXT NOT NULL`、`INTEGER NOT NULL` | 远程服务器地址与 1～65535 端口 |
| `config_json` | `TEXT NOT NULL` | 协议专用参数 JSON，不重复保存上列公共字段 |

`subscription_id` 外键使用 `ON DELETE RESTRICT`。`nodes` 保存解析后的字段，不保存原始分享 URI。

同一 Subscription 内的 `name` 使用 SQLite `BINARY` 比较并建立唯一索引：

```sql
CREATE UNIQUE INDEX ux_nodes_subscription_name
ON nodes(subscription_id, name COLLATE BINARY)
WHERE subscription_id IS NOT NULL;
```

这个约束按原始 `name` 区分大小写、前后空白和 Unicode 字符；不同 Subscription 及自建 Node 可以重名。

### 1.3 `inbounds`

| 字段 | 类型与约束 | 含义 |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Inbound 标识 |
| `name` | `TEXT NOT NULL` | 展示名称 |
| `protocol` | 枚举文本 | `http`、`socks`、`mixed`、`shadowsocks`、`vmess` |
| `listen_address`、`listen_port` | 规范化 IP 文本、1～65535 整数 | 本地监听位置 |
| `config_json` | `TEXT NOT NULL` | 认证及协议专用参数 JSON |

`UNIQUE(listen_address, listen_port)` 防止相同地址和端口重复。

### 1.4 `outbounds` 与 `outbound_nodes`

| 表 | 字段 | 类型与约束 | 含义 |
|---|---|---|---|
| `outbounds` | `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | MANUAL/AUTO 标识 |
|  | `name`、`type` | `TEXT NOT NULL`；`type` 为 `manual` 或 `auto` | 展示名称和控制方式 |
|  | `default_node_id` | `INTEGER NOT NULL` | Pool 中持久化的 Default Node |
| `outbound_nodes` | `outbound_id`、`node_id` | 复合主键，分别引用 Outbound、Node | Node Pool 成员 |
|  | `priority` | `INTEGER NOT NULL`，同 Pool 内唯一 | 数值越小，顺序越靠前 |

`outbound_nodes` 对 Outbound 使用 `ON DELETE CASCADE`，对 Node 使用 `ON DELETE RESTRICT`。`PRIMARY KEY(outbound_id, node_id)` 防止 Pool 内重复 Node，`UNIQUE(outbound_id, priority)` 防止 priority 重复。

Default Node 与成员关系使用复合外键保证：

```sql
FOREIGN KEY (id, default_node_id)
    REFERENCES outbound_nodes(outbound_id, node_id)
    DEFERRABLE INITIALLY DEFERRED
```

该外键在事务提交时校验 Default Node 属于对应 Pool。

### 1.5 `routes` 与 DIRECT

| 字段 | 类型与约束 | 含义 |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Route 标识 |
| `inbound_id` | `INTEGER NOT NULL UNIQUE`，外键 | 每个 Inbound 最多对应一条 Route |
| `target_kind` | `TEXT NOT NULL` | `direct` 或 `outbound` |
| `target_outbound_id` | `INTEGER NULL`，外键 | MANUAL/AUTO 的 ID；DIRECT 时为 `NULL` |

数据库约束要求 `target_kind='direct'` 时 `target_outbound_id IS NULL`；`target_kind='outbound'` 时必须有有效 Outbound ID。目标 Outbound 的 MANUAL/AUTO 类型由 `outbounds.type` 读取，不在 Route 中重复保存。DIRECT 没有数据库行，Route 通过 `target_kind='direct'` 表示它。

Route 对 Inbound 和 Outbound 的外键使用 `ON DELETE RESTRICT`。多个 Route 可以指向同一个 Outbound。

### 1.6 数据库基础约束

数据库初始化采用 WAL；每个 SQLite 连接启用 `PRAGMA foreign_keys=ON` 和 `busy_timeout=5000` 毫秒。数据库约束负责外键、枚举、端口范围、唯一成员、唯一 priority、Default Node 成员关系和 Route 目标形态。

实现复合外键时使用显式事务与延迟校验；SQLite 对延迟外键、`RESTRICT` 的即时行为及部分唯一索引的规则见[官方外键文档](https://www.sqlite.org/foreignkeys.html)和[部分索引文档](https://www.sqlite.org/partialindex.html)。

## 2. 业务约束与更新规则

### 2.1 Node 来源与身份

自建 Node 的 `subscription_id=NULL`，可由用户新增、编辑和删除。订阅 Node 的 `subscription_id` 固定为所属 Subscription；其字段只由 Sync 写入。Sync 对同名 Node 更新时保留 `id`，只修改协议、地址、端口和协议参数；改名相当于删除旧 Node 并新增新 Node，不迁移旧 Node 的 Pool 成员关系。

Pool 成员移除只删除 `outbound_nodes` 的关联行，Node 仍是全局实体。删除全局 Node 才触发它在所有 Pool 中的成员移除及第 4 章的级联判断。

### 2.2 Node Pool、priority 与 Default Node

创建 MANUAL/AUTO 时在一个事务内写入 Outbound、至少两个不同 Node 的 Pool 和 Default Node。未显式选择 Default Node 时，选当前 priority 最小的成员。正常编辑 Pool 后仍须至少两个成员；如果原 Default Node 被移出，选剩余 priority 最小的成员。删除全局 Node 时的不足两成员处理见第 4 章。MANUAL 与 AUTO 转换只更新 `type`，Pool、priority、Default Node 和引用它的 Route 保持原关联。

AUTO 的 Candidate 是 Pool 中除 Default Node 外的成员，直接按 `outbound_nodes.priority` 排序；Default Node 同时是 Fallback Node。数据层不另存 Candidate 顺序或 Fallback 标识。

MANUAL 在线选择的目标必须属于该 Pool。已被 Route 引用时，实际切换成功后更新 `default_node_id`；未被 Route 引用时，只更新 `default_node_id`。AUTO 的 Current Node 由运行控制管理，不通过人工选择修改数据库 Default Node；切换时序及失败处理由 05 设计确定。

新 Pool 按提交顺序分配 `10, 20, 30…` 的 priority；追加成员使用当前最大值加 `10`。插入指定位置时优先使用相邻 priority 之间的空闲正整数；插入首位时使用小于现有最小值的正整数。没有空位时，才在同一事务中将此 Pool 重新编号为 `10, 20, 30…`。移除成员时保留其他成员原 priority，因此间隔可以存在。

在线重排只接受完整的现有成员 ID 列表，成员集合必须与当前 Pool 完全一致，且没有重复。顺序未变则保持原 priority；顺序变化时，在运行控制锁内开启事务，先为这些成员分配互不冲突的临时负数，再按提交顺序写入 `10, 20, 30…`，最后提交，避免 SQLite 的即时唯一性校验碰到中间冲突。持久化 priority 由 Service 保证为正数。该操作保持成员、Default Node 和 Current Node 不变；AUTO 下次择优时读取数据库中的最新 priority。

### 2.3 Inbound 监听冲突

保存 Inbound 时将监听地址解析为规范化 IPv4 或 IPv6 字面量，并与其他 Inbound（含尚未关联 Route 的 Inbound）、ProxyHub Web 监听位置比较。端口不同则不冲突；端口相同按以下规则判定：

| 地址组合 | 结果 |
|---|---|
| 相同具体 IP | 冲突 |
| `0.0.0.0` 与任意 IPv4 | 冲突 |
| `::` 与任意 IPv4 或 IPv6 | 冲突，按双栈占用保守处理 |
| 不同的具体 IPv4；或不同的具体 IPv6 | 不冲突 |
| 具体 IPv4 与具体 IPv6 | 不冲突 |

IPv4 映射的 IPv6 地址按对应 IPv4 处理。Web Listen Address 同样按 IP 字面量校验；冲突判断使用与启动时相同的 Web Listen Address 和 Web Port。保存前的 Service 校验给出被冲突对象及端口，数据库唯一约束再兜底相同地址。监听地址与实际 sing-box 绑定行为的验证放在 04 设计中。

## 3. Subscription 请求、解析与差异

### 3.1 输入与处理顺序

保存 Subscription 时校验 URL 格式与 HTTPS 协议。Sync 使用当前保存的 URL，校验证书并发送 Clash 兼容 User-Agent。旧分支已经支持普通 URI 行列表、Base64 包装的 URI 列表和含 `proxies` 的 Clash YAML；本版先沿用这三种订阅容器格式作为设计候选，具体格式识别需以脱敏的实际订阅响应验证。Node 只接受 V1.0 的五种协议；单条分享 URI 的参数组合由 04 设计定义。

```text
请求并确认响应有效
→ 识别订阅容器、解码、逐项解析并标记不支持或无效的 Node
→ 对有效候选的原始 name 检查同一 Subscription 内重复
→ 按原始 name 执行 Filter / Exclude
→ 校验可入库 Node，生成标准字段
→ 确认最终至少有一个合法 Node
→ 按 name 与数据库现有 Node 计算差异及级联影响
```

Filter/Exclude 关键词按逗号或换行分隔，只修剪关键词并丢弃空项；匹配 Node `name` 时忽略大小写，多个 Filter 为 OR，Exclude 优先。Node `name` 本身保持解析值，不修剪、不改写。重复名称以完整原始 `name` 作区分大小写的比较；发现重复则整个 Sync 失败，不以“后一条覆盖前一条”处理。

请求失败、格式无法识别、重复名称、最终没有合法 Node 或过滤后为空时，Sync 停止且数据库不变。无效/不支持 Node 作为跳过项进入预览；跳过项不进入目标 Node 集合，因此同名旧 Node 仍可能出现在删除预览中。

### 3.2 身份差异与元信息

差异只在同一 Subscription 内按 `name` 计算：

| 旧库与新结果 | 数据动作 |
|---|---|
| 同名且字段相同 | 保留原 Node ID 和字段 |
| 同名但字段变化 | 保留 Node ID，更新变化字段 |
| 新结果独有名称 | 插入新 Node |
| 旧库独有名称 | 将旧 Node 放入待删除集合 |

改名表现为“一条删除 + 一条新增”，新 Node 获得新 ID。Subscription URL、Filter 或 Exclude 的普通编辑只更新 Subscription 行；已有 Node 等待下一次 Sync 才变化。

Subscription Refresh 在 `running` 和 `stopped` 均可执行，独立于运行控制锁。它使用同一个当前 URL 获取流量和到期元信息，只更新 `subscriptions` 的元信息字段及成功时间。缺失的元信息字段保留原值；Refresh 不运行 Node Parser，也不改变 Node 或 Pool。请求结束写入前检查 Subscription 仍存在且 URL 与请求开始时相同，避免将旧 URL 的元信息写到新配置上。

## 4. 级联预览与原子修改

### 4.1 统一影响计划

Subscription Sync、删除 Subscription、删除一个或多个 Node、删除 Inbound 及删除 MANUAL/AUTO 使用同一套影响计算。计划至少包含：

- 直接新增、修改、删除及跳过的 Node；
- 受影响 Pool 的成员变化、保留的 priority 和 Default Node 替换；
- 因不足两个 Node 而删除的 MANUAL/AUTO；
- 因 Inbound 或 Outbound 删除而删除的 Route；
- Subscription、Inbound、Outbound 等操作目标本身。

预览对用户展示对象名称、标识、动作和变化字段名；凭据、协议密钥、完整 Subscription URL、原始分享 URI 与原始订阅正文不进入预览。普通删除提供简单确认；一旦产生级联或 Default Node 替换，展示完整影响后确认。

### 4.2 多 Node 删除的最终状态计算

将本次要删除的全局 Node 合并为一个集合，逐个 Outbound 从 Pool 中一次性扣除整个集合，再判断最终成员数：

1. 剩余成员少于两个：将 Outbound 及引用它的全部 Route 加入删除计划。
2. 剩余成员至少两个：保留原有成员 priority；若 Default Node 被删除，取剩余成员中 priority 最小者作为新 Default Node。
3. 多条 Route 引用同一个待删 Outbound 时，把每条 Route 都列入计划；Route 不自动指向 DIRECT。

这个计算同样用于 Subscription 删除和 Sync 的 Node 删除部分。普通 Pool 编辑则按第 2.2 节校验，不能通过编辑把成员数减到两个以下。

### 4.3 Preview、Confirm 与事务

结构修改的 Preview 在管理状态为 `stopped` 时读取数据库并生成影响计划。对于 Sync，服务端在当前进程内暂存本次已解析且校验通过的目标 Node 集合、Subscription 输入快照和预览结果，返回短期确认标识；Confirm 使用这份目标集合，不再次请求订阅。取消、确认完成、超时或进程重启后，这份临时预览失效。

Confirm 取得运行控制锁，确认管理状态为 `stopped`，开启 `BEGIN IMMEDIATE` 事务；用当前数据库及暂存输入重新计算影响计划。如果 Subscription 的 URL/Filter/Exclude 或实际影响与用户看到的预览不同，回滚并要求重新预览。影响一致时，Service 按依赖顺序完成全部更新并提交：

```text
删除将失效的 Route
→ 更新保留 Outbound 的 Default Node
→ 删除需要移除的 Outbound（成员关系随之删除）
→ 删除保留 Outbound 中目标 Node 的成员关系
→ 删除目标 Node
→ 删除操作目标 Subscription / Inbound（如适用）
→ 插入或更新本次 Sync 的 Node、Subscription 元信息（如适用）
→ 检查剩余 Outbound 的 Pool 与外键约束
→ COMMIT
```

实际 SQL 可按外键依赖调整局部顺序，但一次用户确认只有一个事务；任一步失败整体回滚。Subscription Sync 的 Node、Default Node、Outbound、Route 和相关 Subscription 元信息一起提交。Preview 后如果管理状态变为 `running`，Confirm 在写入前拒绝执行。

### 4.4 可检查样例

**Node 删除与级联。** Outbound A 的 Pool 为 `N11(10, Default)、N12(20)、N13(30)`；Outbound B 为 `N11(10, Default)、N14(20)`，两者各有 Route。删除 N11 后，A 保留 N12、N13，priority 仍为 20、30，Default 变为 N12；B 只剩 N14，因而删除 B 及其 Route。两部分在同一事务中生效。

**Subscription 改名。** 旧数据为 `甲(id=21)`、`乙(id=22)`；新结果为内容变化的 `甲` 和 `丙`。预览显示更新 id=21、删除 id=22、新增 `丙`，并继续列出 id=22 所在 Pool 的影响；确认后 `丙` 使用新 ID。

**priority 在线重排。** Pool 原顺序为 `A(10)、B(20)、C(30)`，提交 `C、A、B`。成员集合完全相同，事务内分配临时 priority 后写为 `C(10)、A(20)、B(30)`；Default Node 与 Current Node 保持原值。

## 5. 后续设计衔接

04 设计确定 `nodes.config_json` 和 `inbounds.config_json` 的协议字段、订阅样例与 sing-box 映射；05 设计确定运行时 Current Node 与健康状态的内存结构；06、07 设计预览展示、确认标识和错误响应。03 的数据库中只保存业务持久状态，不保存 Current Node、健康结果或 AUTO 计时。

本稿的订阅容器格式沿用旧分支的能力作为候选；仍需用实际订阅的脱敏响应，确认 URI 行列表、Base64 包装和 Clash YAML 是否覆盖首版输入。验证结果决定 03 的格式范围及 04 的解析样例。
