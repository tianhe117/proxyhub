# ProxyHub V1.0 数据模型设计

> 文档状态：待审核
> 更新日期：2026-09-18
> 上游文档：[需求规范](01-requirements.md)、[软件架构设计](02-architecture.md)

本文定义业务表、关联、数据库约束及数据变更后的持久化规则，对应需求中的实体关系、订阅 Node 身份、Node Pool 和级联删除。协议参数字段与 sing-box 映射由 04 设计确定。

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
| `outbound_id` | `INTEGER NULL`，外键指向 `outbounds.id` | `NULL` 表示 DIRECT；非空表示 MANUAL/AUTO |

Route 行存在即表示已选择目标；`outbound_id=NULL` 专指 DIRECT，非空值必须指向现有的 MANUAL/AUTO。DIRECT 没有数据库行。目标 Outbound 的类型由 `outbounds.type` 读取，不在 Route 中重复保存。

Route 对 Inbound 和 Outbound 的外键使用 `ON DELETE RESTRICT`。多个 Route 可以指向同一个 Outbound。

### 1.6 数据库基础约束

数据库初始化采用 WAL；每个 SQLite 连接启用 `PRAGMA foreign_keys=ON` 和 `busy_timeout=5000` 毫秒。数据库约束负责外键、枚举、端口范围、唯一成员、唯一 priority 和 Default Node 成员关系。

实现复合外键时使用显式事务与延迟校验；SQLite 对延迟外键、`RESTRICT` 的即时行为及部分唯一索引的规则见[官方外键文档](https://www.sqlite.org/foreignkeys.html)和[部分索引文档](https://www.sqlite.org/partialindex.html)。

## 2. 数据约束与持久化规则

### 2.1 Node 身份与归属

订阅 Node 以同一 Subscription 内的原始 `name` 作为身份键。同名更新保留 `nodes.id`；名称变化对应删除旧 Node、插入新 Node，新 Node 获得新 ID。自建 Node 的 `subscription_id` 为 `NULL`，不参与订阅名称唯一约束。

Node 是全局数据，`outbound_nodes` 只保存 Pool 成员关系。从一个 Pool 移除成员只删除关联行；删除全局 Node 时，须先处理它在所有 Pool 中的关联。

### 2.2 Node Pool 与 Default Node

每个保留的 MANUAL/AUTO 在事务提交时至少有两个不同 Node。复合外键保证 Default Node 属于其 Pool；成员数由跨行校验保证。创建时未指定 Default Node，或保留的 Pool 中原 Default Node 被移除时，持久化 priority 最小的成员为新的 Default Node。

同一 Pool 的 priority 唯一，最终保存值为正整数，允许间隔。成员顺序变化只更新相关 priority；MANUAL/AUTO 类型转换只更新 `outbounds.type`，成员、Default Node 和引用它的 Route 保持原关联。

### 2.3 删除后的关联状态

删除 Subscription 时，一并删除其所属 Node。删除一个或多个全局 Node 时，先从每个受影响 Pool 扣除整个待删除集合，再依据最终成员数处理：

1. 剩余不足两个 Node：删除该 Outbound 及引用它的全部 Route。
2. 剩余至少两个 Node：保留其他成员的 priority；原 Default Node 被删除时，改为剩余成员中 priority 最小者。

删除 Inbound 或 Outbound 时，一并删除引用它的 Route；Route 不自动改指 DIRECT。一次操作涉及的 Node、Pool 成员、Default Node、Outbound 和 Route 变更在同一数据库事务中提交，失败时整体回滚。

## 3. 后续设计衔接

04 设计确定 `nodes.config_json`、`inbounds.config_json` 的协议字段及 sing-box 映射，并承接分享 URI 与订阅内容解析。后续服务、运行控制及接口设计承接订阅请求与 Refresh、监听冲突校验、priority 调整、运行时 Node 切换及级联预览确认。
