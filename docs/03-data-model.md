# ProxyHub V1.0 数据模型设计

> 文档状态：已确认
> 更新日期：2026-09-18
> 上游文档：[需求规范](01-requirements.md)、[软件架构设计](02-architecture.md)

本文定义业务表、关联及数据约束，对应需求中的实体关系、订阅 Node 身份和 Node Pool。

## 1. 表结构

表名和字段名是本设计的实现契约。时间字段采用 UTC Unix 秒；未知元信息使用 `NULL`，不以 `0` 表示未知。`nodes.config_json` 与 `inbounds.config_json` 仅定义存储列，不约束协议专用参数的具体键。

### 1.1 `subscriptions`

| 字段 | 类型与约束 | 含义 |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Subscription 标识 |
| `name` | `TEXT NOT NULL` | 展示名称 |
| `url` | `TEXT NOT NULL` | 当前订阅地址 |
| `filter_text`、`exclude_text` | `TEXT NOT NULL DEFAULT ''` | 用户输入的筛选词原文 |
| `upload_bytes` | `INTEGER NULL CHECK(upload_bytes >= 0)` | 已使用的上传流量 |
| `download_bytes` | `INTEGER NULL CHECK(download_bytes >= 0)` | 已使用的下载流量 |
| `total_bytes` | `INTEGER NULL CHECK(total_bytes >= 0)` | 总流量 |
| `expires_at`、`refreshed_at` | `INTEGER NULL` | 到期时间、最近成功 Refresh 时间 |

`name` 和 `url` 不设唯一约束；Subscription 可以暂时没有关联 Node。

### 1.2 `nodes`

| 字段 | 类型与约束 | 含义 |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | 全局 Node 标识 |
| `subscription_id` | `INTEGER NULL`，外键指向 `subscriptions.id` | `NULL` 表示自建；非空表示所属 Subscription |
| `name` | `TEXT NOT NULL` | 展示名称；订阅 Node 的身份匹配值 |
| `protocol` | `TEXT NOT NULL CHECK(protocol IN ('vmess', 'vless', 'trojan', 'shadowsocks', 'hysteria2'))` | Node 协议 |
| `address`、`port` | `TEXT NOT NULL`；`INTEGER NOT NULL CHECK(port BETWEEN 1 AND 65535)` | 远程服务器地址与端口 |
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
| `protocol` | `TEXT NOT NULL CHECK(protocol IN ('http', 'socks', 'mixed', 'shadowsocks', 'vmess'))` | Inbound 协议 |
| `listen_address`、`listen_port` | `TEXT NOT NULL`；`INTEGER NOT NULL CHECK(listen_port BETWEEN 1 AND 65535)` | 本地监听位置；地址保存为规范化 IP 文本 |
| `config_json` | `TEXT NOT NULL` | 认证及协议专用参数 JSON |

`UNIQUE(listen_address, listen_port)` 防止相同地址和端口重复。通配地址与具体地址之间的监听冲突由应用层校验。

### 1.4 `outbounds` 与 `outbound_nodes`

| 表 | 字段 | 类型与约束 | 含义 |
|---|---|---|---|
| `outbounds` | `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | MANUAL/AUTO 标识 |
|  | `name`、`type` | `TEXT NOT NULL`；`TEXT NOT NULL CHECK(type IN ('manual', 'auto'))` | 展示名称和控制方式 |
|  | `default_node_id` | `INTEGER NOT NULL` | Pool 中持久化的 Default Node |
| `outbound_nodes` | `outbound_id`、`node_id` | 均为 `INTEGER NOT NULL`；复合主键，分别引用 Outbound、Node | Node Pool 成员 |
|  | `priority` | `INTEGER NOT NULL CHECK(priority > 0)`，同 Pool 内唯一 | 数值越小，顺序越靠前；允许不连续 |

`outbound_nodes` 对 Outbound 使用 `ON DELETE CASCADE`，对 Node 使用 `ON DELETE RESTRICT`。前者只在删除 Outbound 时清理成员行，不会根据成员数量反向删除 Outbound。`PRIMARY KEY(outbound_id, node_id)` 防止 Pool 内重复 Node，`UNIQUE(outbound_id, priority)` 防止 priority 重复。

Default Node 与成员关系使用复合外键保证：

```sql
FOREIGN KEY (id, default_node_id)
    REFERENCES outbound_nodes(outbound_id, node_id)
    DEFERRABLE INITIALLY DEFERRED
```

该外键在事务提交时校验 Default Node 属于对应 Pool。每个 Outbound 至少有两个不同 Node；成员数量是跨行约束，由应用层在提交前校验，外键本身无法保证。priority 重排时的中间值也必须满足正数检查和唯一约束。

### 1.5 `routes` 与 DIRECT

| 字段 | 类型与约束 | 含义 |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Route 标识 |
| `inbound_id` | `INTEGER NOT NULL UNIQUE`，外键 | 每个 Inbound 最多对应一条 Route |
| `outbound_id` | `INTEGER NULL`，外键指向 `outbounds.id` | `NULL` 表示 DIRECT；非空表示 MANUAL/AUTO |

Route 行存在即表示已选择目标；`outbound_id=NULL` 专指 DIRECT，非空值必须指向现有的 MANUAL/AUTO。DIRECT 没有数据库行。目标 Outbound 的类型由 `outbounds.type` 读取，不在 Route 中重复保存。由于 `NULL` 已表示 DIRECT，创建 Route 时是否显式选择目标由应用层校验。

Route 对 Inbound 和 Outbound 的外键使用 `ON DELETE RESTRICT`。多个 Route 可以指向同一个 Outbound。

### 1.6 数据库基础约束

数据库初始化采用 WAL；每个 SQLite 连接启用 `PRAGMA foreign_keys=ON` 和 `busy_timeout=5000` 毫秒。数据库使用外键、`CHECK`、主键及唯一索引约束单行取值和已建立的关联；Pool 成员数量、监听地址重叠及 Route 目标是否显式选择由应用层校验。

实现复合外键时使用显式事务与延迟校验；SQLite 对延迟外键、`RESTRICT` 的即时行为及部分唯一索引的规则见[官方外键文档](https://www.sqlite.org/foreignkeys.html)和[部分索引文档](https://www.sqlite.org/partialindex.html)。
