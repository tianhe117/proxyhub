# ProxyHub V1.0 sing-box 集成设计

> 文档版本：v0.1
> 文档状态：起草中
> 更新日期：2026-09-20
> 需求基线：[ProxyHub V1.0 需求规范](01-requirements.md)
> 架构基线：[ProxyHub V1.0 软件架构设计](02-architecture.md)
> 数据基线：[ProxyHub V1.0 数据模型设计](03-data-model.md)

本文定义 ProxyHub 业务数据到 sing-box 运行配置的映射，以及配置检查替换、控制接口、子进程适配和二进制管理。本版先确定整体结构，并完整承接 Node 数据到 sing-box Outbound 的映射；其余章节先确定职责和后续详细设计的位置。

主要对应需求：REQ-GEN-003～004、REQ-CONFIG-001～021、REQ-OUTBOUND-007、REQ-RUNTIME-001～007、REQ-HEALTH-003、REQ-UPGRADE-001～003、REQ-REL-001～002。

## 1. 集成边界与组成

### 1.1 职责

`app/singbox/` 是 ProxyHub 与 sing-box 的唯一集成边界，内部按以下职责组织：

| 组件 | 职责 |
|---|---|
| 配置生成器 | 读取调用方提供的数据库业务快照，生成完整的 sing-box 配置对象 |
| 配置文件管理器 | 写入临时配置、调用配置检查、原子替换正式配置并保留最近一次成功配置 |
| 控制接口客户端 | 查询 selector 当前选择、切换 Node，并执行健康检测所需的 URL test |
| 子进程适配器 | 启动、停止、等待和观察唯一 sing-box 子进程 |
| 二进制管理器 | 读取本地版本、检查远程版本、下载、验证和原子替换二进制 |

集成层不决定 Subscription 差异、Node Pool 成员、Default Node、AUTO 候选顺序或管理状态转换。这些业务结论由调用方提供；集成层负责把已确定的数据转换成有效配置或执行明确的引擎操作。

### 1.2 数据边界

以下两个 JSON 概念必须区分：

| 名称 | 含义 |
|---|---|
| `nodes.config_json` | 数据库中单个 Node 的规范协议参数，是配置生成器的输入 |
| sing-box `config.json` | 汇总 Node、Inbound、Outbound、Route 和控制能力后生成的完整运行文件 |

配置生成器只读取数据库快照和必要 Settings，不从既有 sing-box `config.json` 反向恢复业务数据。生成文件是运行产物，数据库始终是业务数据的权威来源。

### 1.3 主要处理路径

```text
数据库业务快照 + Settings
  → 配置生成器
  → 临时 sing-box config.json
  → sing-box check
  → 原子替换正式配置
  → 子进程适配器启动 sing-box

Runtime 明确操作
  → 控制接口客户端
  → 查询 selector、切换 Node 或执行 URL test

下载或升级请求
  → 临时二进制
  → 完整性、架构、可执行性和版本验证
  → 原子替换正式二进制
```

## 2. 文档结构

后续详细设计按下列顺序组织，Node 映射已经在第 3 章展开：

| 章节 | 内容 |
|---|---|
| 3 | Node 数据到 sing-box Outbound 的字段映射 |
| 4 | 完整配置的生成范围、顶层结构和固定能力 |
| 5 | Node、DIRECT、MANUAL/AUTO 的 tag、selector 和 Route 映射 |
| 6 | Inbound 映射 |
| 7 | 配置检查、文件替换和失败保护 |
| 8 | 控制接口、Current Node 查询与切换 |
| 9 | 子进程启动、停止和状态观察 |
| 10 | 二进制版本、下载、验证和升级 |
| 11 | 配置样例与集成验证 |

## 3. Node Outbound 映射

### 3.1 输入与输出

每条合法 `nodes` 记录生成一个独立 sing-box Outbound，是否被 MANUAL/AUTO 引用不影响生成。

| 数据库输入 | Outbound 输出 |
|---|---|
| `protocol` | `type`；`shadowsocks`、`hysteria2` 使用完整类型名 |
| Node tag 规划结果 | `tag` |
| `address` | `server` |
| `port` | `server_port` |
| `config_json` | 对应协议字段、TLS、Transport 和网络范围 |

Node 名称不作为配置引用标识。名称允许修改且可能含空白或特殊字符；tag 必须由稳定数据库 ID 按第 5 章规则生成。

### 3.2 通用网络字段

`nodes.config_json.network` 缺省时不生成 Outbound `network`，表示使用 sing-box 的协议默认能力；值为 `tcp` 或 `udp` 时原值写入。该字段与 V2Ray Transport 的类型无关，Transport 为普通 TCP 只表示没有额外传输封装。

### 3.3 TLS

数据库中没有 `tls` 对象时不生成 Outbound `tls`。存在时按下表映射：

| `nodes.config_json.tls` | sing-box Outbound `tls` |
|---|---|
| `enabled` | `enabled` |
| `server_name` | `server_name` |
| `insecure` | `insecure` |
| `alpn` | `alpn` |
| `utls.enabled` | `utls.enabled` |
| `utls.fingerprint` | `utls.fingerprint` |
| `reality.enabled` | `reality.enabled` |
| `reality.public_key` | `reality.public_key` |
| `reality.short_id` | `reality.short_id` |

配置生成器不重新解释输入别名或文本布尔值。数据库中的对象已经通过 Node 校验，生成器只验证结构完整性并执行确定映射。`reality` 仅用于 VLESS；其他协议出现该对象时配置生成失败。

### 3.4 V2Ray Transport

VMess、VLESS 和 Trojan 的 `transport` 对象按类型映射：

| 数据库 Transport | sing-box Transport |
|---|---|
| `type=ws`、`path`、可选 `headers.Host` | WebSocket `type`、`path`、`headers.Host` |
| `type=http`、`path`、可选 `host` | HTTP `type`、`path`、`host` |
| `type=grpc`、可选 `service_name` | gRPC `type`、`service_name` |

数据库没有 `transport` 时不生成该字段。配置生成器不根据未知类型降级为普通 TCP；遇到数据库契约之外的类型或字段组合时，完整配置生成失败。

### 3.5 VMess

| `nodes.config_json` | VMess Outbound |
|---|---|
| `uuid` | `uuid` |
| `security` | `security` |
| `alter_id` | `alter_id` |
| `network` | 通用 `network` |
| `tls` | 通用 TLS |
| `transport` | 通用 V2Ray Transport |

### 3.6 VLESS

| `nodes.config_json` | VLESS Outbound |
|---|---|
| `uuid` | `uuid` |
| `flow` | `flow` |
| `network` | 通用 `network` |
| `tls` | 通用 TLS，包括 Reality |
| `transport` | 通用 V2Ray Transport |

### 3.7 Trojan

| `nodes.config_json` | Trojan Outbound |
|---|---|
| `password` | `password` |
| `network` | 通用 `network` |
| `tls` | 通用 TLS；必须启用 |
| `transport` | 通用 V2Ray Transport |

### 3.8 Shadowsocks

| `nodes.config_json` | Shadowsocks Outbound |
|---|---|
| `method` | `method` |
| `password` | `password` |
| `network` | 通用 `network` |
| `plugin.type` | `plugin` |
| `plugin` 的其余结构化字段 | 生成规范 `plugin_opts` 文本 |

`plugin` 不存在时不生成 `plugin` 或 `plugin_opts`。存在时使用以下确定规则：

- `obfs-local`：输出 `obfs=<mode>`，存在 `host` 时追加 `;obfs-host=<host>`。
- `v2ray-plugin`：从 `mode=<mode>` 开始，再依次追加适用的 `;host=<host>`、`;path=<path>`、`;tls`。
- 写入 `plugin_opts` 前，按照插件选项格式转义反斜杠、分号和等号。

生成器只接受数据库 Node 参数契约规定的插件类型和字段组合。未知插件或选项使完整配置生成失败，不能丢弃插件后继续生成。

### 3.9 Hysteria2

| `nodes.config_json` | Hysteria2 Outbound |
|---|---|
| `password` | `password` |
| `up_mbps` | `up_mbps` |
| `down_mbps` | `down_mbps` |
| `obfs.type` | `obfs.type` |
| `obfs.password` | `obfs.password` |
| `obfs.min_packet_size` | `obfs.min_packet_size` |
| `obfs.max_packet_size` | `obfs.max_packet_size` |
| `network` | 通用 `network` |
| `tls` | 通用 TLS；必须启用 |

### 3.10 兼容性和失败处理

Node 输入阶段已经校验 ProxyHub V1.0 接受的协议参数。配置生成器仍应对数据库记录进行结构校验，避免数据库损坏、旧版本遗留数据或人工修改生成不完整 Outbound。

目标 sing-box 版本不支持某个已保存参数、字段映射失败或生成结果未通过 `sing-box check` 时，整个配置生成失败。失败不修改数据库，不替换正式配置，也不使用旧配置启动。

## 4. 完整配置生成范围

完整配置必须同时生成日志、DNS、所需 Inbound、全部合法 Node Outbound、被 Route 引用的 MANUAL/AUTO selector、必要的 DIRECT Outbound、全部 Route 以及控制接口所需配置。具体顶层 JSON 结构和固定 Settings 映射在本章后续补齐。

生成范围遵循以下边界：所有合法 Node 都生成；只有被 Route 引用的 Inbound 和 MANUAL/AUTO 生成；Route 指向 DIRECT 时生成系统内置 DIRECT；所有有效 Route 都进入配置；Node Pool priority 不进入配置。

## 5. Tag、Selector 与 Route

tag 使用稳定数据库 ID 生成，不使用可修改名称。Node、Inbound、MANUAL/AUTO 和 DIRECT 使用不同前缀，保证全局唯一并便于控制接口定位。MANUAL/AUTO 使用 selector 表达 Node Pool，启动配置中的默认选择来自数据库 Default Node；具体 tag 格式、selector 字段和 Route 规则在本章补齐。

## 6. Inbound 映射

本章定义 HTTP、SOCKS、mixed、redirect 和 TUN 的 `inbounds.config_json` 到 sing-box Inbound 映射，并处理监听地址、端口、认证和协议专属参数。只有被 Route 引用的 Inbound 进入运行配置。

## 7. 配置检查与文件替换

配置生成到同目录临时文件，调用目标二进制执行配置检查。检查成功后才原子替换正式配置，并更新最近一次成功运行配置；任一步失败均保留原正式文件和最近一次成功文件。正式文件替换成功不代表进程启动成功，两类结果分别返回。

## 8. 控制接口

本章定义 Current Node 查询、MANUAL/AUTO selector 切换、URL test 和连接中断使用的控制接口，以及超时、响应校验和失败结果。控制客户端只执行 Runtime 明确下发的操作，不自行决定切换目标。

## 9. 子进程适配

ProxyHub 最多管理一个 sing-box 子进程。子进程适配器负责启动参数、标准输出与错误接入日志、优雅停止、超时后的强制停止、退出状态和存活检查；管理状态及恢复策略由 Runtime 决定。

## 10. 二进制管理

二进制管理器负责本地版本读取、远程版本检查、下载和升级。下载先进入临时文件，验证完整性、amd64 架构、可执行性和版本信息后原子替换正式二进制。任一步失败都保留原文件；管理状态为 `running` 时调用方禁止下载或升级。

## 11. 验证范围

后续补充可直接执行的最小配置样例，至少覆盖五种 Node、五种 Inbound、DIRECT、MANUAL、AUTO、Route、控制接口、配置检查失败、进程退出以及二进制升级失败保护。Node 映射测试应读取脱敏数据库 Node 数据，验证生成 Outbound 后再执行 `sing-box check`。

## 12. 设计依据

- [sing-box VMess outbound](https://sing-box.sagernet.org/configuration/outbound/vmess/)
- [sing-box VLESS outbound](https://sing-box.sagernet.org/configuration/outbound/vless/)
- [sing-box Trojan outbound](https://sing-box.sagernet.org/configuration/outbound/trojan/)
- [sing-box Shadowsocks outbound](https://sing-box.sagernet.org/configuration/outbound/shadowsocks/)
- [sing-box Hysteria2 outbound](https://sing-box.sagernet.org/configuration/outbound/hysteria2/)
- [sing-box TLS fields](https://sing-box.sagernet.org/configuration/shared/tls/)
- [sing-box V2Ray Transport](https://sing-box.sagernet.org/configuration/shared/v2ray-transport/)
