# ProxyHub V1.0 Node 与 Subscription 输入解析设计

> 文档版本：v0.1
> 文档状态：待确认
> 更新日期：2026-09-20
> 需求基线：[ProxyHub V1.0 需求规范](01-requirements.md)
> 数据基线：[ProxyHub V1.0 数据模型设计](03-data-model.md)

本文定义五种远程 Node 的统一输入契约、单条分享 URI 解析、Subscription 的 HTTPS 获取与内容解析、Filter/Exclude、重复名称处理和 Refresh 元信息。解析结果使用 `nodes` 表规定的 `name`、`protocol`、`address`、`port`、`config_json` 字段。

主要对应需求：REQ-NODE-001～006、REQ-CONFIG-007、REQ-SUB-001～012、REQ-REL-002。

## 1. 模块边界与处理结果

### 1.1 职责划分

| 位置 | 职责 |
|---|---|
| `app/parser/` | 识别订阅格式，解析分享 URI 和 Clash YAML，将外部字段转换为统一 Node 数据；不访问网络和数据库 |
| `app/services/` | 获取 Subscription、调用 Parser、应用 Filter/Exclude、检查重复名称，并把候选 Node、跳过信息和元信息交给业务操作 |
| Node 统一校验器 | 校验页面表单、分享 URI 和 Subscription 产生的 Node；三个入口使用同一组字段规则 |

Parser 是确定性的纯解析模块：相同输入产生相同 Node 或问题结果。网络错误、数据库事务和级联变更不进入 Parser。

### 1.2 标准 Node

解析成功的 Node 包含以下数据：

| 字段 | 规则 |
|---|---|
| `name` | 字符串；Subscription Node 必须非空；按输入解码后的完整内容保留，不修剪、不改写、不做 Unicode 归一化 |
| `protocol` | 统一为 `vmess`、`vless`、`trojan`、`shadowsocks`、`hysteria2` 之一 |
| `address` | 非空域名、IPv4 或 IPv6；去除 URI 中 IPv6 的方括号后保存，不包含空白或控制字符 |
| `port` | 1～65535 的整数 |
| `config_json` | 协议参数组成的 JSON 对象；不重复保存名称、协议、地址和端口 |

外部输入中的 `ss` 统一映射为数据库协议值 `shadowsocks`，`hy2` 统一映射为 `hysteria2`。JSON 使用 snake_case 键，输出时固定排序，便于稳定比较。同一语义只保存一种字段名，不保留外部格式的别名或原始分享 URI。

单条分享 URI 可以没有名称，此时只回填协议参数，由用户填写名称后才能保存。Subscription 中缺少名称、名称为空字符串、名称只含空白或名称不是字符串的条目属于无效 Node。其他名称即使带有前后空白也按原值保存并参与身份匹配。

### 1.3 解析问题

每个订阅条目的处理结果分为三类：

| 类别 | 含义 | 是否进入候选 Node |
|---|---|---|
| `invalid` | 协议受支持，但 URI/YAML 结构、必要字段或字段值无效 | 否 |
| `unsupported` | 协议、传输方式、插件或关键能力不在 V1.0 支持范围 | 否 |
| `warning` | Node 可以完整表达，但输入还包含已忽略的非关键字段 | 是 |

问题记录只包含条目序号、可安全显示的 Node 名称、协议、类别和概括原因。错误消息可以说明字段名，不包含密码、UUID、密钥、服务器地址、完整 URI、完整 Subscription URL 或原始条目。

## 2. 通用协议参数

### 2.1 TLS 参数

VMess、VLESS、Trojan 和 Hysteria2 使用相同的 TLS 对象：

| 键 | 类型 | 规则 |
|---|---|---|
| `enabled` | 布尔值 | VMess/VLESS 可选；Trojan/Hysteria2 固定为 `true` |
| `server_name` | 字符串，可选 | TLS Server Name；缺省时由 sing-box 使用服务器地址 |
| `insecure` | 布尔值 | 是否跳过 Node 服务器证书验证；缺省为 `false` |
| `alpn` | 字符串数组，可选 | 数组成员必须为非空字符串 |
| `utls_fingerprint` | 字符串，可选 | uTLS 指纹；仅在输入明确提供时保存 |
| `reality` | 对象，可选 | 只用于 VLESS，包含 `public_key` 和可选 `short_id` |

TLS 未启用时不保存其余 TLS 参数。布尔字段只接受布尔值、`0/1` 以及大小写不敏感的 `true/false`，其他文本不作真假推断。

### 2.2 V2Ray Transport 参数

VMess、VLESS 和 Trojan 支持以下传输形式：

| `transport.type` | 保存参数 | 外部别名 |
|---|---|---|
| `ws` | `path`、可选 `headers.Host` | Clash `ws-opts`，URI `type=ws` |
| `http` | `path`、可选 `host` 字符串数组 | `h2` 统一映射为 `http` |
| `grpc` | `service_name` | Clash `grpc-opts`，URI `type=grpc` |

没有 Transport 时不保存 `transport`，表示普通 TCP 传输。输入明确指定其他传输类型时跳过该 Node，并记录 `unsupported`，不将其降级为 TCP。

外部 VMess JSON 的 `net` 和 Clash 的 `network` 表示 Transport；值为 `tcp` 时表示没有额外 Transport。`config_json.network` 表示 sing-box Outbound 可承载的目标网络，是另一项参数；Clash `udp: false` 映射为 `network=tcp`，`udp: true` 时省略并使用 sing-box 默认值。

### 2.3 通用校验

- UUID 使用标准 UUID 文本，解析后保存为小写带连字符形式。
- 密码、UUID、密钥、加密方法等必要文本不得为空。地址、UUID 和枚举值可以去除结构性的外围空白；密码和密钥按解码后的完整内容保存，不自动修剪。
- URI 的 percent-encoding 和 Base64 必须能完整解码为 UTF-8；解码失败时拒绝该条目。
- 未知字段不会自动进入 `config_json`。未知的非关键字段产生 `warning`；会改变连接方式的未知取值产生 `unsupported`。
- 页面逐项填写、单条 URI 回填和 Subscription 导入最终都经过标准 Node 校验，避免三个入口接受不同的数据。

## 3. 五种 Node 协议

### 3.1 VMess

| `config_json` 键 | 必要性与规则 |
|---|---|
| `uuid` | 必填，有效 UUID |
| `security` | 必填；支持 `auto`、`none`、`zero`、`aes-128-gcm`、`chacha20-poly1305`、`aes-128-ctr` |
| `alter_id` | 可选，缺省为 `0`，必须为非负整数 |
| `network` | 可选，`tcp`、`udp` 或省略表示两者 |
| `tls`、`transport` | 按第 2 章规则保存 |

分享 URI 支持 `vmess://` 后接 Base64 JSON。字段映射为：`ps` → 名称、`add` → 地址、`port` → 端口、`id` → UUID、`scy/security` → `security`、`aid` → `alter_id`、`net` → Transport 类型。`host`、`path`、`sni/serverName`、`alpn`、`fp`、`allowInsecure` 映射到相应 Transport 或 TLS 字段。

VMess JSON 必须是对象。`type` 是旧格式的传输附加参数，不作为 VMess 加密方法；`type` 非空且不是 `none` 时，如果无法无损映射则跳过该 Node。

### 3.2 VLESS

| `config_json` 键 | 必要性与规则 |
|---|---|
| `uuid` | 必填，有效 UUID |
| `flow` | 可选；为空或 `xtls-rprx-vision` |
| `network` | 可选，`tcp`、`udp` 或省略表示两者 |
| `tls`、`transport` | 按第 2 章规则保存 |

VLESS 分享 URI 采用 `vless://uuid@host:port?...#name`。`encryption` 缺省和唯一支持值均为 `none`。`security` 支持空值、`none`、`tls` 和 `reality`；Reality 必须同时提供 public key，short id 存在时必须是长度不超过 16 的偶数位十六进制文本。

URI 的 `type`、`host`、`path`、`serviceName` 映射到 Transport；`sni/servername`、`alpn`、`fp/fingerprint`、`insecure/allowInsecure` 映射到 TLS；`pbk/public-key`、`sid/short-id` 映射到 Reality。

### 3.3 Trojan

| `config_json` 键 | 必要性与规则 |
|---|---|
| `password` | 必填，保留 percent-decoding 后的完整内容 |
| `network` | 可选，`tcp`、`udp` 或省略表示两者 |
| `tls` | 必填且 `enabled=true` |
| `transport` | 可选，按第 2 章规则保存 |

Trojan 分享 URI 采用 `trojan://password@host:port?...#name`。Transport 与 TLS 查询参数使用和 VLESS 相同的映射；不能关闭 TLS。

### 3.4 Shadowsocks

| `config_json` 键 | 必要性与规则 |
|---|---|
| `method` | 必填，必须是 sing-box 支持的 Shadowsocks 加密方法 |
| `password` | 必填，保留解码后的完整内容 |
| `plugin` | 可选，仅支持 `obfs-local`、`v2ray-plugin` |
| `plugin_opts` | 使用插件时可选，保存为 sing-box 接受的选项文本 |
| `network` | 可选，`tcp`、`udp` 或省略表示两者 |

V1.0 固定接受以下 Shadowsocks 2022、AEAD 和 legacy 方法：

- `2022-blake3-aes-128-gcm`、`2022-blake3-aes-256-gcm`、`2022-blake3-chacha20-poly1305`；
- `none`、`aes-128-gcm`、`aes-192-gcm`、`aes-256-gcm`、`chacha20-ietf-poly1305`、`xchacha20-ietf-poly1305`；
- `aes-128-ctr`、`aes-192-ctr`、`aes-256-ctr`、`aes-128-cfb`、`aes-192-cfb`、`aes-256-cfb`、`rc4-md5`、`chacha20-ietf`、`xchacha20`。

分享 URI 支持 SIP002：`ss://userinfo@host:port?...#name`。`userinfo` 可以是 Base64URL 编码的 `method:password`，也可以按 SIP002 直接使用 percent-encoded 的 `method:password`。同时兼容旧格式 `ss://Base64(method:password@host:port)#name`。Base64 接受标准和 URL-safe 字母表，可缺少尾部 padding。

URI 的 `plugin` 参数按 SIP002 解码为插件名和选项。Clash `plugin: obfs` 映射为 `obfs-local`；其他插件只有在 sing-box 原生支持时才能导入。插件不受支持时跳过整个 Node，避免保存一个丢失插件后无法连接的配置。

### 3.5 Hysteria2

| `config_json` 键 | 必要性与规则 |
|---|---|
| `password` | 必填 |
| `up_mbps`、`down_mbps` | 可选，存在时为正整数 |
| `obfs` | 可选对象；V1.0 支持 `salamander`，启用时必须包含非空 `password` |
| `network` | 可选，`tcp`、`udp` 或省略表示两者 |
| `tls` | 必填且 `enabled=true` |

分享 URI 支持 `hysteria2://` 和 `hy2://`，userinfo 为 password；省略端口时使用标准默认值 443。`sni/peer`、`insecure/allowInsecure`、`alpn` 映射到 TLS；`up/up_mbps`、`down/down_mbps` 映射到带宽；`obfs-password/obfs_password` 映射到混淆密码。证书 pin、ECH 等无法无损映射的连接参数使该 Node 记为 `unsupported`，不能静默丢弃。

`hysteria://` 属于另一协议标识，不作为 Hysteria2 别名。端口跳跃、多端口和无法由 `address + port` 完整表达的输入在 V1.0 中记为 `unsupported`。

## 4. 单条分享 URI

### 4.1 页面回填流程

```text
用户粘贴一条 URI
  → 识别 scheme
  → 解码并解析协议字段
  → 执行统一 Node 校验
  → 回填 Node 表单
  → 用户检查或修改
  → 保存时再次执行统一校验
```

输入必须恰好包含一条 URI；多行内容、Subscription URL 和 Base64 包装的 URI 列表不属于单条回填。解析只回填表单，不直接写数据库。解析失败时保留用户当前表单内容，并返回协议及概括原因。

URI scheme 大小写不敏感，查询参数按各协议已知别名读取；同一个参数重复出现时使用最后一个值并给出 `warning`。Fragment 经过一次 percent-decoding 后作为名称，不将 `+` 当作空格。

### 4.2 名称与敏感信息

名称从 VMess `ps` 或其他 URI 的 Fragment 取得。解析器不生成 `Unnamed` 等替代名称。名称缺失不阻止回填，但保存前必须由用户提供非空名称。

页面可以在输入框中短暂持有原始 URI用于解析，请求完成后不持久化。API 响应只返回解析字段和安全错误，不回显原始 URI；服务端日志只记录协议和结果类别。

## 5. Subscription 获取与格式识别

### 5.1 URL 与 HTTPS 请求

保存 Subscription 时先校验 URL 是包含主机的绝对 HTTPS URL。Sync 和 Refresh 使用当前保存的完整 URL 发起 GET 请求，并遵循以下规则：

| 项目 | 设计值 |
|---|---|
| User-Agent | `ClashForAndroid/2.5.12` |
| Accept | `*/*` |
| Accept-Encoding | `identity` |
| TLS | 使用系统 CA，校验证书有效期和主机名 |
| 超时 | connect 30 秒、read 30 秒 |
| 重定向 | 最多 3 次；每个目标仍必须是 HTTPS，并正常验证证书 |
| 成功状态 | HTTP 2xx |
| Sync 响应体上限 | HTTP 传输及内容解码后、Base64 外层解码前最多 8 MiB |

请求头不携带 Cookie 或来自管理页面的认证信息。`Content-Type` 只用于诊断，不参与格式拒绝或选择；实际样本中合法 Clash YAML 可能以 `text/html` 返回。完整 URL 及其 query/token 不写日志，错误中只显示 Subscription 名称或数据库 ID。

Sync 严格按 UTF-8 解码响应体，可接受开头的 UTF-8 BOM。无效 UTF-8、超过大小限制、非 2xx、TLS 失败、超时或超过重定向次数均视为请求/响应失败。

### 5.2 支持的响应格式

| 格式 | 识别条件 | 解析范围 |
|---|---|---|
| Clash YAML | YAML 根为对象，顶层 `proxies` 为数组 | 只读取 `proxies`，忽略 `proxy-groups`、`rules`、DNS、端口等完整 Clash 配置 |
| URI 列表 | 至少有一个非空行以 URI scheme 开始 | 每个非空行作为一个条目；`#` 开头的独立注释行忽略 |
| Base64 包装 | 整个响应去除空白后可作标准或 URL-safe Base64 解码，解码结果为 UTF-8 且能识别为前两种格式 | 对解码后的 Clash YAML 或 URI 列表继续解析 |

格式识别顺序为：尝试受约束的 Base64 外层、检查 Clash YAML 顶层结构、检查 URI 列表。Base64 解码结果无法识别时回到原始正文判断，避免把普通文本误判为 Base64。URI 列表允许只包含不受支持的代理 scheme，以便给出逐条 `unsupported` 结果；HTML 登录页、纯数字正文、没有顶层 `proxies` 的普通 YAML 和其他任意文本均为未知格式。

YAML 使用 safe loader，禁止 alias，最大嵌套深度为 64，最多组合 20,000 个 YAML 节点。单次响应最多处理 5,000 个 `proxies` 条目或 URI 行；超过限制时整个 Sync 失败。YAML 语法错误或顶层 `proxies` 不是数组属于格式失败，不尝试从破损 YAML 中截取局部内容。

### 5.3 Clash Proxy 映射

Clash 条目的 `name`、`type`、`server`、`port` 映射为标准 Node 公共字段。`type: ss` 映射为 `shadowsocks`，`type: hy2` 映射为 `hysteria2`。五种协议的其余常用字段按第 2、3 章映射：

- `skip-cert-verify` → `tls.insecure`；
- `servername/sni`、`alpn`、`client-fingerprint/fingerprint` → TLS；
- `ws-opts`、`h2-opts`、`grpc-opts` → Transport；
- `reality-opts.public-key/short-id` → VLESS Reality；
- `cipher` → VMess security 或 Shadowsocks method；
- Hysteria2 的 `password/auth`、`up/down`、`obfs/obfs-password` → 对应协议参数。

顶层 `proxies` 中的每个条目独立解析。一个条目无效或不受支持不会阻止其他条目解析；条目中已知但无法表达的连接能力会使该条目跳过，普通未知字段只记录字段名警告。

## 6. Subscription Sync 解析规则

### 6.1 处理顺序

```text
校验 URL 与 HTTPS 获取
  → UTF-8/Base64 解码和格式识别
  → 按条目解析五种协议
  → 统一 Node 校验
  → 检查合法 Node 的重复名称
  → Filter
  → Exclude
  → 输出候选 Node、跳过信息和统计
```

格式可识别后，无效协议条目和不受支持条目分别记录并跳过。不存在“最低有效率”阈值：只要至少有一个合法 Node、没有重复名称，并且筛选后仍有 Node，解析阶段即可成功。这样不会因订阅中混有较多其他协议而拒绝所需的合法节点。

### 6.2 重复名称

重复名称在所有已成功解析并通过 Node 校验的条目中检查，发生在 Filter/Exclude 之前。比较使用完整名称和大小写敏感的精确字符串比较：

- `Node-A` 与 `node-a` 不同；
- `Node-A` 与 `Node-A ` 不同；
- 不做 Unicode 大小写折叠或归一化；
- 相同名称出现两次即使字段完全一致，本次 Sync 也失败；
- 筛选条件不能隐藏重复名称错误。

无效或不受支持条目不参与重复检查，因为它们不能形成候选 Node。失败结果只列出重复名称和所在条目序号，不显示两个条目的敏感字段。

### 6.3 Filter 与 Exclude

Filter 和 Exclude 的关键词分别按逗号或换行拆分，去除每个关键词首尾空白并丢弃空项。匹配仅针对保留原值的 Node `name`，使用 Unicode `casefold` 后的包含判断，不改变保存的名称。

| 条件 | 结果 |
|---|---|
| Filter 没有有效关键词 | 所有合法 Node 进入下一步 |
| Filter 有关键词 | 名称包含任一关键词的 Node 进入下一步 |
| Exclude 命中任一关键词 | 排除该 Node |
| 同时命中 Filter 和 Exclude | Exclude 优先，排除该 Node |

被 Filter/Exclude 排除的条目单独计数，不属于 `invalid` 或 `unsupported`。筛选后为零个 Node 时 Sync 失败。

### 6.4 成功与失败输出

成功的解析结果包含：响应格式、是否使用 Base64 外层、候选 Node、各类跳过条目、警告和筛选数量。调用方以候选 Node 的完整名称与现有 Subscription Node 比较。

以下情况使本次 Sync 在解析阶段失败：

- HTTPS 请求或响应校验失败；
- 响应格式未知，或 YAML/Base64/UTF-8 无法正确解析；
- 响应超过资源限制；
- 没有任何合法 Node；
- 合法 Node 中存在重复名称；
- Filter/Exclude 后没有 Node。

上述失败均不产生可确认的 Node 变更，原有 Subscription 和 Node 数据保持不变。成功解析中的 `invalid`、`unsupported` 和 `warning` 随候选结果进入差异预览；被跳过的原订阅 Node 仍可因不在候选结果中进入删除范围。

## 7. Subscription Refresh 元信息

Refresh 使用与 Sync 相同的 URL、请求头、HTTPS、证书、超时和重定向规则，但只读取响应状态及响应头，不识别或解析响应正文，也不产生 Node 候选结果。

`Subscription-Userinfo` 按分号分隔 `key=value`，键名大小写不敏感：

| Header 键 | 数据库字段 | 规则 |
|---|---|---|
| `upload` | `upload_bytes` | 非负十进制整数，单位为 byte |
| `download` | `download_bytes` | 非负十进制整数，单位为 byte |
| `total` | `total_bytes` | 非负十进制整数，单位为 byte |
| `expire` | `expires_at` | 正整数 UTC Unix 秒；明确返回 `0` 时保存 `NULL` |

未知键忽略。缺少或无效的已知键不覆盖数据库中原值；服务端明确给出合法值时只更新对应字段。HTTPS 请求成功即更新 `refreshed_at`，即使响应没有可用的流量字段，同时向页面说明未返回可用元信息。请求失败时所有元信息及 `refreshed_at` 保持不变。

Sync 只处理 Node 内容，不更新上述元信息或 `refreshed_at`。这样 Sync 与 Refresh 的数据效果保持独立。

## 8. 安全、资源限制与日志

- Subscription URL、分享 URI、响应正文及 Node `config_json` 不写日志。
- 请求和解析日志使用 Subscription ID、格式、数量、问题类别和安全原因；不记录响应头原文，因为其中可能出现账号页面 URL 或其他标识。
- 差异预览可显示 Node 名称、协议和变更字段名；密码、UUID、密钥、地址及敏感字段值不显示。
- 解析器不执行 YAML 自定义类型、alias、模板、脚本或外部引用。
- HTTP 响应以流式方式执行 8 MiB 上限，不能只依赖可能缺失或伪造的 `Content-Length`。
- 请求失败、格式失败和资源限制均返回简短稳定的错误类别，详细异常只记录异常类型，不拼接原始输入。

## 9. 验证数据与检查场景

### 9.1 已提交脱敏样本

测试数据位于 [`tests/fixtures/input_parsing/cases.yaml`](../tests/fixtures/input_parsing/cases.yaml)，作为 04 设计、实现和回归验证的共同输入。文件不含真实 Subscription URL、token 或 Node 凭据，也不要求连接外部服务器。

| 样本 | 主要检查 | 预期 |
|---|---|---|
| `share-uri-ss-non-live` | Shadowsocks SIP002、Base64 userinfo、Fragment 名称 | 解析并回填；协议统一为 `shadowsocks` |
| `share-uri-vmess-non-live` | VMess Base64 JSON、WebSocket、TLS | 解析并回填；不执行连通性测试 |
| `share-uri-vless-invalid` | 无有效 UUID 和标准 authority | 拒绝，且错误不回显 URI 内容 |
| `clash-hy2-response` | 完整 HTTP 头、Clash YAML、3 个 Hysteria2 Node、额外 proxy groups/rules | 只导入 3 个 `proxies`；读取 Refresh 元信息；忽略其他 Clash 配置 |
| `clash-ss-response` | `text/html` Content-Type、chunked 响应、3 个 Shadowsocks Node | 依据正文识别 YAML，不受 Content-Type 误导 |

HTTP fixture 同时保存了真实响应中观察到的请求头、响应头顺序、正文结构和无关字段，敏感域名、token、密码及节点地址已替换。测试读取 fixture，不向原始订阅地址发起网络请求。

### 9.2 必须补齐的表驱动样本

实现时在同一 fixture 中补充小型脱敏输入，覆盖：

1. VLESS TLS、VLESS Reality、Trojan、Hysteria2 URI 的有效解析；
2. 五种协议在 Clash `proxies` 中的字段映射；
3. URI 列表、标准/Base64URL 包装、缺 padding、UTF-8 BOM 和 CRLF；
4. 名称大小写、前后空白、Unicode、重复名称及 Filter/Exclude 优先级；
5. 无效 UUID、端口、布尔值、TLS/Reality、Transport、Shadowsocks method/plugin 和 Hysteria2 obfs；
6. 未知格式、HTML、纯数字正文、破损 YAML、alias、超深 YAML、超大正文和超过 5,000 条；
7. HTTPS 证书失败、HTTP URL、重定向到 HTTP、超时、非 2xx 及 URL 脱敏；
8. `Subscription-Userinfo` 的部分字段、未知字段、负数、非整数、`expire=0`、缺失 Header；
9. Sync 不更新元信息，Refresh 不解析或修改 Node，所有失败保持原数据。

单元测试验证 Parser 和统一 Node 校验；HTTP 测试使用本地受控响应或 mock transport 验证请求头、TLS/重定向和资源上限；业务集成测试验证候选结果及失败时数据库不变。fixture 中的非 live Node 只验证解析和字段映射，不以连接成功作为预期。

## 10. 设计依据

- [sing-box VMess outbound](https://sing-box.sagernet.org/configuration/outbound/vmess/)
- [sing-box VLESS outbound](https://sing-box.sagernet.org/configuration/outbound/vless/)
- [sing-box Trojan outbound](https://sing-box.sagernet.org/configuration/outbound/trojan/)
- [sing-box Shadowsocks outbound](https://sing-box.sagernet.org/configuration/outbound/shadowsocks/)
- [sing-box Hysteria2 outbound](https://sing-box.sagernet.org/configuration/outbound/hysteria2/)
- [sing-box TLS fields](https://sing-box.sagernet.org/configuration/shared/tls/)
- [sing-box V2Ray Transport](https://sing-box.sagernet.org/configuration/shared/v2ray-transport/)
- [Shadowsocks SIP002 URI Scheme](https://github.com/shadowsocks/shadowsocks-org/wiki/SIP002-URI-Scheme)
- [Hysteria2 URI Scheme](https://v2.hysteria.network/docs/developers/URI-Scheme/)
