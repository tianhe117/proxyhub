# ProxyHub V1.0 Node 与 Subscription 输入解析设计

> 文档版本：v0.4
> 文档状态：待确认
> 更新日期：2026-09-20
> 需求基线：[ProxyHub V1.0 需求规范](01-requirements.md)
> 数据基线：[ProxyHub V1.0 数据模型设计](03-data-model.md)

本文定义五种远程 Node 的数据库输入契约、单条分享 URI 解析、Subscription 的 HTTPS 获取与内容解析、Filter/Exclude、重复名称处理和 Refresh 元信息。解析结果使用 `nodes` 表规定的 `name`、`protocol`、`address`、`port`、`config_json` 字段；`nodes.config_json` 是 ProxyHub 保存的 Node 协议参数，不是运行配置文件。

主要对应需求：REQ-NODE-001～006、REQ-CONFIG-007、REQ-SUB-001～012、REQ-REL-002。

第 1～7 章是主要设计，供方案和流程评审；附录给出开发所需的精确数据契约、协议映射和错误码。

## 1. 设计概览

### 1.1 模块职责

| 位置 | 职责 |
|---|---|
| `app/parser/` | 识别订阅格式，解析分享 URI 和 Clash YAML，将外部字段转换为统一 Node 数据；不访问网络和数据库 |
| `app/services/` | 获取 Subscription、调用 Parser、应用 Filter/Exclude、检查重复名称，并把标准 Node、问题记录和元信息交给业务操作 |
| Node 统一校验器 | 校验页面表单、分享 URI 和 Subscription 产生的 Node；三个入口使用同一组字段规则 |

Parser 是确定性的纯解析模块：相同输入产生相同 Node 或问题结果。它不读取或写入数据库，也不生成运行配置。网络请求由 Service 执行，数据库事务和级联变更由业务操作处理。

### 1.2 输入处理路径

```text
单条分享 URI ─→ Parser ─→ 统一 Node ─→ 页面回填 ─→ 保存前校验

Subscription URL ─→ HTTPS 获取 ─→ 格式识别 ─→ 条目解析
                 ─→ 统一校验 ─→ 重复名称检查 ─→ Filter/Exclude
                 ─→ 标准 Node 与问题记录

Subscription Refresh ─→ HTTPS 获取 ─→ 响应头解析 ─→ 元信息结果
```

Sync 解析 Node 正文，Refresh 解析流量和到期时间响应头。两条流程复用相同的 HTTPS 请求约束，但各自只更新职责范围内的数据。

### 1.3 关键设计结论

| 主题 | 设计结论 |
|---|---|
| Node 结构 | 五种协议统一输出 `name`、`protocol`、`address`、`port` 和协议专属 `config` |
| 协议范围 | 支持 VMess、VLESS、Trojan、Shadowsocks、Hysteria2；外部 `ss`、`hy2` 转换为完整协议名 |
| 统一校验 | 页面表单、分享 URI 和 Subscription 使用同一组 Node 字段规则 |
| 单条 URI | 只解析并回填表单，不直接写数据库；名称可以稍后由用户补充 |
| Subscription 格式 | 支持 Clash YAML、URI 列表及二者外层的 Base64 包装；依据正文识别，不依赖 `Content-Type` |
| 条目容错 | 单个无效或不支持的条目被跳过并记录问题，不阻断其他条目 |
| 重复名称 | 在所有合法 Node 中、Filter/Exclude 之前检查；存在重复即使本次 Sync 失败 |
| 筛选顺序 | 先 Filter，再 Exclude；Exclude 命中时排除 |
| 数据边界 | Parser 输出与数据库字段一致的标准 Node 或元信息；持久化、差异计算和事务不属于本设计 |
| 敏感数据 | URL、分享 URI、响应正文和连接凭据不进入日志及问题消息 |

## 2. 单条分享 URI

### 2.1 页面回填流程

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

URI scheme 大小写不敏感，查询参数按协议已知别名读取；同一个参数重复出现时使用最后一个值并给出 `warning`。Fragment 经过一次 percent-decoding 后作为名称，不将 `+` 当作空格。

URI query 中的 `remarks`、`remark`、`name` 和 `udp` 只影响展示或客户端能力，忽略并记录 warning；其他未映射 query 参数可能改变连接语义，整条 Node 记为 `unsupported`。VMess Base64 JSON 中的未知标量字段按 warning 处理，未知对象或 `*-opts` 按 unsupported 处理。

### 2.2 名称与敏感信息

名称从 VMess `ps` 或其他 URI 的 Fragment 取得。解析器不生成 `Unnamed` 等替代名称。名称缺失不阻止回填，但保存前必须由用户提供非空名称。

页面可以在输入框中短暂持有原始 URI 用于解析，请求完成后不持久化。API 响应只返回解析字段和安全错误，不回显原始 URI；服务端日志只记录协议和结果类别。

## 3. Subscription 获取与格式识别

### 3.1 HTTPS 请求

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

### 3.2 响应格式

| 格式 | 识别条件 | 解析范围 |
|---|---|---|
| Clash YAML | YAML 根为对象，顶层 `proxies` 为数组 | 只读取 `proxies`，忽略 `proxy-groups`、`rules`、DNS、端口等完整 Clash 配置 |
| URI 列表 | 至少有一个非空行以 URI scheme 开始 | 每个非空行作为一个条目；`#` 开头的独立注释行忽略 |
| Base64 包装 | 整个响应去除空白后可作标准或 URL-safe Base64 解码，解码结果为 UTF-8 且能识别为前两种格式 | 对解码后的 Clash YAML 或 URI 列表继续解析 |

格式识别顺序为：尝试受约束的 Base64 外层、检查 Clash YAML 顶层结构、检查 URI 列表。Base64 解码结果无法识别时回到原始正文判断，避免把普通文本误判为 Base64。URI 列表允许只包含不受支持的代理 scheme，以便给出逐条 `unsupported` 结果；HTML 登录页、纯数字正文、没有顶层 `proxies` 的普通 YAML 和其他任意文本均为未知格式。

YAML 使用 safe loader，禁止 alias，最大嵌套深度为 64，最多组合 20,000 个 YAML 节点。单次响应最多处理 5,000 个 `proxies` 条目或 URI 行；超过限制时整个 Sync 失败。YAML 语法错误或顶层 `proxies` 不是数组属于格式失败，不尝试从破损 YAML 中截取局部内容。

## 4. Subscription Sync

### 4.1 处理顺序

```text
校验 URL 与 HTTPS 获取
  → UTF-8/Base64 解码和格式识别
  → 按条目解析五种协议
  → 统一 Node 校验
  → 检查合法 Node 的重复名称
  → Filter
  → Exclude
  → 输出候选 Node、问题记录和统计
```

格式可识别后，无效协议条目和不受支持条目分别记录并跳过。不存在最低有效率阈值：只要至少有一个合法 Node、没有重复名称，并且筛选后仍有 Node，解析阶段即可成功。订阅中混有其他协议不会导致所需的合法 Node 被整体拒绝。

Parser 逐条处理并保持原订阅顺序。合法条目进入重复检查和筛选；`invalid`、`unsupported` 条目只进入问题记录；可完整表达但忽略了非关键字段的条目进入候选结果并带有 `warning`。精确输出契约和处理伪代码见附录 A。

### 4.2 重复名称

重复名称在所有已成功解析并通过 Node 校验的条目中检查，发生在 Filter/Exclude 之前。比较使用完整名称和大小写敏感的精确字符串比较：

- `Node-A` 与 `node-a` 不同；
- `Node-A` 与 `Node-A ` 不同；
- 不做 Unicode 大小写折叠或归一化；
- 相同名称出现两次即使字段完全一致，本次 Sync 也失败；
- 筛选条件不能隐藏重复名称错误。

无效或不受支持条目不参与重复检查，因为它们不能形成候选 Node。失败结果只列出重复名称和所在条目序号，不显示两个条目的敏感字段。

### 4.3 Filter 与 Exclude

Filter 和 Exclude 的关键词分别按逗号或换行拆分，去除每个关键词首尾空白并丢弃空项。匹配仅针对保留原值的 Node `name`，使用 Unicode `casefold` 后的包含判断，不改变保存的名称。

| 条件 | 结果 |
|---|---|
| Filter 没有有效关键词 | 所有合法 Node 进入下一步 |
| Filter 有关键词 | 名称包含任一关键词的 Node 进入下一步 |
| Exclude 命中任一关键词 | 排除该 Node |
| 同时命中 Filter 和 Exclude | Exclude 优先，排除该 Node |

被 Filter/Exclude 排除的条目单独计数，不属于 `invalid` 或 `unsupported`。筛选后为零个 Node 时 Sync 失败。

### 4.4 解析结果

成功结果包含响应格式、是否使用 Base64 外层、标准 Node、问题记录和各项数量。Node 已完成输入规范化，可以作为后续数据库操作的输入；解析器不读取现有 Subscription Node，也不计算新增、修改或删除差异。

请求、格式、资源限制、无合法 Node、重复名称或筛选结果为空均使解析失败。失败结果不包含可供保存的 Node。成功结果保留 `invalid`、`unsupported` 和 `warning`，供调用方展示或记录；稳定失败码见附录 E。

## 5. Subscription Refresh 元信息

Refresh 使用与 Sync 相同的 URL、请求头、HTTPS、证书、超时和重定向规则，但只读取响应状态及响应头，不识别或解析响应正文，也不产生 Node 候选结果。

`Subscription-Userinfo` 按分号分隔 `key=value`，键名大小写不敏感：

| Header 键 | 数据库字段 | 规则 |
|---|---|---|
| `upload` | `upload_bytes` | 非负十进制整数，单位为 byte |
| `download` | `download_bytes` | 非负十进制整数，单位为 byte |
| `total` | `total_bytes` | 非负十进制整数，单位为 byte |
| `expire` | `expires_at` | 正整数 UTC Unix 秒；明确返回 `0` 时保存 `NULL` |

未知键忽略。Header 超过 4 KiB 时整体视为无可用元信息。缺少或无效的已知键不进入解析结果；服务端明确给出合法值时只输出对应字段。HTTPS 请求成功时，Service 在响应完成后把当前 UTC Unix 秒作为 `refreshed_at` 一并输出，即使响应没有可用的流量字段。请求失败时不输出元信息更新结果。

Sync 只解析 Node 内容，不输出上述元信息或 `refreshed_at`。Refresh 只输出元信息结果，不解析或输出 Node。

## 6. 安全、资源限制与日志

- Subscription URL、分享 URI、响应正文及 Node `config_json` 不写日志。
- 请求和解析日志使用 Subscription ID、格式、数量、问题类别和安全原因；不记录响应头原文，因为其中可能出现账号页面 URL 或其他标识。
- 解析问题可以包含 Node 名称、协议和字段名；密码、UUID、密钥、地址及敏感字段值不输出。
- 解析器不执行 YAML 自定义类型、alias、模板、脚本或外部引用。
- HTTP 响应以流式方式执行 8 MiB 上限，不能只依赖可能缺失或伪造的 `Content-Length`。
- 请求失败、格式失败和资源限制均返回简短稳定的错误类别，详细异常只记录异常类型，不拼接原始输入。

## 7. 验证数据与检查场景

### 7.1 已提交脱敏样本

测试数据位于 [`tests/fixtures/input_parsing/cases.yaml`](../tests/fixtures/input_parsing/cases.yaml)，作为本设计、实现和回归验证的共同输入。文件不含真实 Subscription URL、token 或 Node 凭据，也不要求连接外部服务器。

| 样本组 | 主要检查 |
|---|---|
| 五种 `share-uri-*-non-live` | 各协议分享 URI、名称、TLS、Transport、Reality、插件和 obfs 的规范映射 |
| `share-uri-vless-invalid` | 无效 URI 被安全拒绝，错误不回显 URI 内容 |
| `uri-list-base64-filter`、`uri-list-duplicate-name` | Base64URL、Filter/Exclude 及筛选前重复名称检查 |
| `subscription-body-unknown-numeric` | 纯数字正文以 `unknown_format` 失败 |
| `clash-five-protocols-compact` | 五种协议的 Clash YAML 逐字段映射 |
| `clash-hy2-response`、`clash-ss-response` | 完整脱敏 HTTP 响应、正文识别、无关 Clash 字段和 Refresh 元信息 |

HTTP fixture 保留真实响应中观察到的请求头、响应头顺序、正文结构和无关字段，敏感域名、token、密码及 Node 地址已经替换。测试读取 fixture，不向原始订阅地址发起网络请求。

### 7.2 自动化验证矩阵

实现测试必须覆盖以下边界；适合复用的数据继续放入同一 fixture，单一字段边界可在测试中直接构造：

1. 五种协议在小型 Clash `proxies` 中的逐字段映射；
2. VLESS 普通 TLS、标准 Base64 包装、UTF-8 BOM 和 CRLF；
3. 名称大小写、前后空白、Unicode 以及更多 Filter/Exclude 组合；
4. 无效 UUID、端口、布尔值、TLS/Reality、Transport、Shadowsocks method/plugin 和 Hysteria2 obfs；
5. HTML、破损 YAML、alias、超深 YAML、超大正文和超过 5,000 条；
6. HTTPS 证书失败、HTTP URL、重定向到 HTTP、超时、非 2xx 及 URL 脱敏；
7. `Subscription-Userinfo` 的部分字段、未知字段、负数、非整数、`expire=0`、缺失 Header；
8. Sync 不输出元信息，Refresh 不解析或输出 Node，请求失败时不产生数据库输入结果。

单元测试验证 Parser 和统一 Node 校验；HTTP 测试使用本地受控响应或 mock transport 验证请求头、TLS/重定向和资源上限；Service 测试验证输出结果可以转换为数据库字段。fixture 中的非 live Node 只验证解析和字段映射，不以连接成功作为预期。

## 附录 A：Parser 数据契约与算法

### A.1 解析问题

每个订阅条目的处理结果分为三类：

| 类别 | 含义 | 是否进入候选 Node |
|---|---|---|
| `invalid` | 协议受支持，但 URI/YAML 结构、必要字段或字段值无效 | 否 |
| `unsupported` | 协议、传输方式、插件或关键能力不在 V1.0 支持范围 | 否 |
| `warning` | Node 可以完整表达，但输入还包含已忽略的非关键字段 | 是 |

问题记录只包含条目序号、可安全显示的 Node 名称、协议、类别和概括原因。错误消息可以说明字段名，不包含密码、UUID、密钥、服务器地址、完整 URI、完整 Subscription URL 或原始条目。

每个被跳过的条目只产生一条终止性 issue，优先级依次为：语法或公共字段无效、协议必要字段无效、已知字段组合无效、不支持的连接能力。warning 只为最终接受的 Node 生成，一个被忽略字段对应一条 warning。

### A.2 输入输出契约

单条 URI 解析返回一个 `NodeDraft`。完整 Subscription 输入链返回一个 `SubscriptionInputResult`：Parser 产生正文解析字段，Service 在同一结构上补充请求失败。这里规定数据含义，不要求实现使用特定 Python 类。

| 结果 | 字段 | 含义 |
|---|---|---|
| `NodeDraft` | `name` | 解码后的名称；单条 URI 中可以为 `NULL`，Subscription 中必须为非空字符串 |
|  | `protocol`、`address`、`port`、`config` | 标准 Node 字段；`config` 是写入 `config_json` 前的对象 |
|  | `warnings` | 此 Node 已忽略的非关键字段名，不包含字段值 |
| `SubscriptionInputResult` | `source_format` | `clash_yaml`、`uri_list` 或请求/识别失败时的 `NULL` |
|  | `base64_wrapped` | 是否成功去除了 Base64 外层 |
|  | `nodes` | 通过解析、统一校验、重复检查和筛选的标准 Node，保持原订阅顺序 |
|  | `issues` | `invalid`、`unsupported` 和 `warning` 记录，保持条目顺序 |
|  | `counts` | 固定包含 `source_entries`、`valid_before_filter`、`invalid`、`unsupported`、`warnings`、`filtered`、`candidates` |
|  | `failure_code` | 成功时为 `NULL`；失败时使用附录 E 的稳定类别 |

`issues` 的 `entry` 从 1 开始：Clash YAML 使用 `proxies` 数组序号，URI 列表使用忽略空行和独立注释行后的条目序号。每条 issue 包含 `entry`、可选的 `name`、可选的 `protocol`、`kind`、`field` 和安全消息。单条 URI 解析失败只返回一条同结构 issue。

`counts.source_entries` 是参与解析的条目数，`valid_before_filter` 是统一校验后的合法 Node 数，`invalid` 和 `unsupported` 按终止性 issue 计数，`warnings` 按 warning 记录计数，`filtered` 是被 Filter 或 Exclude 排除的 Node 数，`candidates` 是最终候选 Node 数。

Parser 不返回数据库 ID，也不把 `config` 序列化为 JSON 字符串。Service 在进入数据比较前，以 UTF-8、键名排序、紧凑分隔符序列化 `config_json`，使相同配置得到相同文本。

### A.3 格式识别伪代码

```text
decode_and_detect(body):
    严格 UTF-8 解码并去除开头 BOM
    尝试将全文空白移除后作标准/Base64URL 解码
    如果解码文本可识别为 Clash YAML 或 URI 列表：
        使用解码文本，并标记 base64_wrapped
    否则继续使用原文

    如果 YAML 根对象含顶层 proxies：按 Clash YAML 处理
    否则如果存在以 URI scheme 开头的条目：按 URI 列表处理
    否则返回 unknown_format
```

### A.4 候选构建伪代码

```text
build_candidates(entries, filter_text, exclude_text):
    按原顺序逐条解析并执行统一 Node 校验
    invalid 或 unsupported → 记录 issue 后跳过
    合法 Node → 保留，warning 与 Node 关联

    没有合法 Node → no_valid_nodes
    按名称原值分组；任一组多于一个 Node → duplicate_name

    对合法 Node 执行 Filter，再执行 Exclude
    结果为空 → filtered_empty
    返回保持原订阅顺序的候选 Node、issues 和 counts
```

### A.5 Refresh 解析伪代码

```text
parse_refresh_response(response):
    请求失败或状态不是 2xx → 返回请求失败
    解析 Subscription-Userinfo 中每个已知键
    合法且明确出现的键 → 加入元信息结果
    缺失或无效的键 → 不加入结果
    expire=0 → 在结果中设置 expires_at=NULL
    加入响应完成时的 refreshed_at 并返回
```

## 附录 B：标准 Node 与通用参数

### B.1 标准 Node

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

### B.2 TLS 参数

VMess、VLESS、Trojan 和 Hysteria2 使用相同的 TLS 对象：

| 键 | 类型 | 规则 |
|---|---|---|
| `enabled` | 布尔值 | VMess/VLESS 可选；Trojan/Hysteria2 固定为 `true` |
| `server_name` | 字符串，可选 | 输入明确指定的 TLS Server Name；没有指定时省略 |
| `insecure` | 布尔值 | 是否跳过 Node 服务器证书验证；缺省为 `false` |
| `alpn` | 字符串数组，可选 | 数组成员必须为非空字符串 |
| `utls` | 对象，可选 | 包含固定的 `enabled=true` 和非空 `fingerprint` |
| `reality` | 对象，可选 | 只用于 VLESS，包含固定的 `enabled=true`、`public_key` 和可选 `short_id` |

TLS 未启用时整个 `tls` 键省略。TLS 对象存在时始终保存 `enabled=true` 和 `insecure`；`server_name`、`alpn`、`utls`、`reality` 仅在有值时保存。布尔字段只接受布尔值、`0/1` 以及大小写不敏感的 `true/false`，其他文本不作真假推断。

uTLS fingerprint 统一转为小写，只接受 `chrome`、`firefox`、`edge`、`safari`、`360`、`qq`、`ios`、`android`、`random`、`randomized`。ALPN 的 Clash 数组保持顺序；URI 中以逗号分隔，去除每项外围空白并拒绝空项。

### B.3 V2Ray Transport 参数

VMess、VLESS 和 Trojan 支持以下传输形式：

| `transport.type` | 保存参数 | 外部别名 |
|---|---|---|
| `ws` | `path`、可选 `headers.Host` | Clash `ws-opts`，URI `type=ws` |
| `http` | `path`、可选 `host` 字符串数组 | `h2` 统一映射为 `http` |
| `grpc` | `service_name` | Clash `grpc-opts`，URI `type=grpc` |

没有 Transport 时不保存 `transport`，表示普通 TCP 传输。输入明确指定其他传输类型时跳过该 Node，并记录 `unsupported`，不将其降级为 TCP。

外部 VMess JSON 的 `net` 和 Clash 的 `network` 表示 Transport；值为 `tcp` 时表示没有额外 Transport。`nodes.config_json.network` 表示 Node 允许承载的目标网络，是另一项参数；Clash `udp: false` 映射为 `network=tcp`，`udp: true` 时省略并表示不限制为单一目标网络。

Transport 的规范化结构固定如下：

| 类型 | `transport` 中保存的键 | 规范化规则 |
|---|---|---|
| WebSocket | `type=ws`、`path`、可选 `headers.Host` | `path` 缺省为 `/`；其他 header 无法无损表达时记为 unsupported |
| HTTP/H2 | `type=http`、`path`、可选 `host` | `path` 缺省为 `/`；只接受字符串或单元素数组；`host` 统一为字符串数组 |
| gRPC | `type=grpc`、可选 `service_name` | 空 service name 省略 |

Clash `ws-opts.path/headers.Host`、`h2-opts.path/host`、`grpc-opts.grpc-service-name` 分别映射到上述结构。URI 使用 `path`、`host`、`serviceName/service_name`。Clash 或 URI 提供的 early data、HTTP 自定义 method/header、gRPC user-agent/连接控制等无法表达的关键 Transport 参数使该 Node 记为 `unsupported`。

### B.4 通用校验

- UUID 使用标准 UUID 文本，解析后保存为小写带连字符形式。
- 地址先去除结构性外围空白；IPv4/IPv6 保存为规范文本，域名经 IDNA 转为小写 ASCII。地址不得包含 scheme、路径、端口、空白、控制字符或 IPv6 zone id。
- 密码、UUID、密钥、加密方法等必要文本不得为空。地址、UUID 和枚举值可以去除结构性的外围空白；密码和密钥按解码后的完整内容保存，不自动修剪。
- URI 的 percent-encoding 和 Base64 必须能完整解码为 UTF-8；解码失败时拒绝该条目。
- 未知字段不会自动进入 `config_json`。未知的非关键字段产生 `warning`；会改变连接方式的未知取值产生 `unsupported`。
- 页面逐项填写、单条 URI 回填和 Subscription 导入最终都经过标准 Node 校验，避免三个入口接受不同的数据。

### B.5 规范化与省略规则

`config_json` 使用以下统一规则，开发时不得由不同解析器自行选择是否保存默认值：

- VMess 的 `security` 和 `alter_id` 始终保存；其他协议只保存自身必填字段。
- `network` 省略表示同时支持 TCP 和 UDP，只在输入明确限制时保存 `tcp` 或 `udp`。
- 未启用 TLS 时省略 `tls`；启用时固定保存 `enabled=true`、`insecure=false/true`。
- 普通 TCP 不保存 `transport`；启用 Transport 时固定保存其 `type` 和该类型的必要字段。
- 可选字符串为空、可选数组为空、可选对象未启用时省略对应键，不保存空字符串、空数组或空对象。
- 数字统一保存为 JSON integer，布尔值统一保存为 JSON boolean，不能保留外部输入中的数字或布尔文本。
- 字段别名同时出现时按各协议映射表中从左到右的优先级取值；值互相冲突时增加 warning，重复的 URI query 参数使用最后一个值。

### B.6 `config_json` 规范形状

`config_json` 只保存协议专属字段，不重复保存 `name`、`protocol`、`address` 和 `port`。顶层字段由附录 C 各协议表定义，`tls`、`transport` 等嵌套对象使用附录 B.2～B.5 的统一形状和省略规则。

测试样本 `share-uri-*-non-live` 和 `clash-five-protocols-compact` 已在 `expected.nodes[].config` 中给出五种协议的完整规范对象。实现应直接以这些对象验证字段层级、JSON 类型和默认值，不再在本文重复一组容易失去同步的示例。

## 附录 C：协议字段映射

### C.1 VMess

| `config_json` 键 | 必要性与规则 |
|---|---|
| `uuid` | 必填，有效 UUID |
| `security` | 必填；支持 `auto`、`none`、`zero`、`aes-128-gcm`、`chacha20-poly1305`、`aes-128-ctr` |
| `alter_id` | 可选，缺省为 `0`，必须为非负整数 |
| `network` | 可选，`tcp`、`udp` 或省略表示两者 |
| `tls`、`transport` | 按附录 B 的通用规则保存 |

分享 URI 支持 `vmess://` 后接 Base64 JSON。字段映射为：`ps` → 名称、`add` → 地址、`port` → 端口、`id` → UUID、`scy/security` → `security`、`aid` → `alter_id`、`net` → Transport 类型。`host`、`path`、`sni/serverName`、`alpn`、`fp`、`allowInsecure` 映射到相应 Transport 或 TLS 字段。

VMess JSON 必须是对象。`type` 是旧格式的传输附加参数，不作为 VMess 加密方法；`type` 非空且不是 `none` 时，如果无法无损映射则跳过该 Node。

| 内部字段 | VMess URI JSON | Clash YAML | 缺省值 |
|---|---|---|---|
| 名称、地址、端口 | `ps`、`add`、`port` | `name`、`server`、`port` | 无 |
| `uuid` | `id` | `uuid` | 无 |
| `security` | `scy`、`security` | `cipher` | `auto` |
| `alter_id` | `aid` | `alterId`、`alter-id` | `0` |
| Transport | `net`，以及 `host/path` | `network`，以及对应 `*-opts` | 普通 TCP |
| TLS 开关 | `tls` | `tls` | `false` |
| TLS Server Name | `sni`、`serverName` | `servername`、`sni` | 省略 |
| TLS insecure | `allowInsecure` | `skip-cert-verify` | `false` |
| uTLS | `fp`、`fingerprint` | `client-fingerprint` | 省略 |

### C.2 VLESS

| `config_json` 键 | 必要性与规则 |
|---|---|
| `uuid` | 必填，有效 UUID |
| `flow` | 可选；为空或 `xtls-rprx-vision` |
| `network` | 可选，`tcp`、`udp` 或省略表示两者 |
| `tls`、`transport` | 按附录 B 的通用规则保存 |

VLESS 分享 URI 采用 `vless://uuid@host:port?...#name`。`encryption` 缺省和唯一支持值均为 `none`。`security` 支持空值、`none`、`tls` 和 `reality`；Reality 必须同时提供 public key，short id 存在时必须是长度不超过 16 的偶数位十六进制文本。

URI 的 `type`、`host`、`path`、`serviceName` 映射到 Transport；`sni/servername`、`alpn`、`fp/fingerprint`、`insecure/allowInsecure` 映射到 TLS；`pbk/public-key`、`sid/short-id` 映射到 Reality。

| 内部字段 | VLESS URI | Clash YAML | 缺省值 |
|---|---|---|---|
| 名称、地址、端口 | Fragment、host、port | `name`、`server`、`port` | 无 |
| `uuid` | userinfo | `uuid` | 无 |
| `flow` | `flow` | `flow` | 省略 |
| encryption 校验 | `encryption` | `encryption` | `none`，不写入 `config_json` |
| Transport | `type` 和对应参数 | `network` 和对应 `*-opts` | 普通 TCP |
| TLS 模式 | `security` | `tls` 或 `reality-opts` | 未启用 |
| TLS Server Name | `sni`、`servername` | `servername`、`sni` | 省略 |
| TLS insecure | `insecure`、`allowInsecure` | `skip-cert-verify` | `false` |
| uTLS | `fp`、`fingerprint` | `client-fingerprint` | 省略 |
| Reality public key | `pbk`、`public-key` | `reality-opts.public-key` | Reality 启用时必填 |
| Reality short id | `sid`、`short-id` | `reality-opts.short-id` | 省略 |

### C.3 Trojan

| `config_json` 键 | 必要性与规则 |
|---|---|
| `password` | 必填，保留 percent-decoding 后的完整内容 |
| `network` | 可选，`tcp`、`udp` 或省略表示两者 |
| `tls` | 必填且 `enabled=true` |
| `transport` | 可选，按附录 B 的通用规则保存 |

Trojan 分享 URI 采用 `trojan://password@host:port?...#name`。Transport 与 TLS 查询参数使用和 VLESS 相同的映射；不能关闭 TLS。

| 内部字段 | Trojan URI | Clash YAML | 缺省值 |
|---|---|---|---|
| 名称、地址、端口 | Fragment、host、port | `name`、`server`、`port` | 无 |
| `password` | userinfo | `password` | 无 |
| Transport | `type` 和对应参数 | `network` 和对应 `*-opts` | 普通 TCP |
| TLS Server Name | `sni`、`servername` | `sni`、`servername` | 省略 |
| TLS insecure | `insecure`、`allowInsecure` | `skip-cert-verify` | `false` |
| uTLS | `fp`、`fingerprint` | `client-fingerprint` | 省略 |

Trojan URI 的 `security` 省略或为 `tls` 时接受，其他值记为 `unsupported`。Clash `reality-opts`、`ss-opts`、ShadowTLS 等扩展不在当前 Trojan 输入范围，不能忽略后继续导入。

### C.4 Shadowsocks

| `config_json` 键 | 必要性与规则 |
|---|---|
| `method` | 必填，必须是 ProxyHub V1.0 接受的 Shadowsocks 加密方法 |
| `password` | 必填，保留解码后的完整内容 |
| `plugin` | 可选对象，仅支持 `obfs-local`、`v2ray-plugin` 及其结构化参数 |
| `network` | 可选，`tcp`、`udp` 或省略表示两者 |

V1.0 固定接受以下 Shadowsocks 2022、AEAD 和 legacy 方法：

- `2022-blake3-aes-128-gcm`、`2022-blake3-aes-256-gcm`、`2022-blake3-chacha20-poly1305`；
- `none`、`aes-128-gcm`、`aes-192-gcm`、`aes-256-gcm`、`chacha20-ietf-poly1305`、`xchacha20-ietf-poly1305`；
- `aes-128-ctr`、`aes-192-ctr`、`aes-256-ctr`、`aes-128-cfb`、`aes-192-cfb`、`aes-256-cfb`、`rc4-md5`、`chacha20-ietf`、`xchacha20`。

分享 URI 支持 SIP002：`ss://userinfo@host:port?...#name`。`userinfo` 可以是 Base64URL 编码的 `method:password`，也可以按 SIP002 直接使用 percent-encoded 的 `method:password`。同时兼容旧格式 `ss://Base64(method:password@host:port)#name`。Base64 接受标准和 URL-safe 字母表，可缺少尾部 padding。

URI 的 `plugin` 参数按 SIP002 解码为插件名和选项。Clash `plugin: obfs` 映射为 `obfs-local`。不在 V1.0 输入范围内的插件使整个 Node 记为 `unsupported`，避免保存缺少连接参数的配置。

| 内部字段 | Shadowsocks URI | Clash YAML | 缺省值 |
|---|---|---|---|
| 名称、地址、端口 | Fragment、host、port | `name`、`server`、`port` | 无 |
| `method` | userinfo 中冒号前内容 | `cipher` | 无 |
| `password` | userinfo 中冒号后完整内容 | `password` | 无 |
| `plugin` 对象 | query `plugin` | `plugin`、`plugin-opts` | 省略 |
| `network` | 无 | `udp: false` → `tcp` | 省略 |

插件选项解析为确定的数据库对象：

- SIP002 中的插件名和选项文本先按转义规则拆分，再与 Clash 插件字段转换为同一对象。
- `obfs-local`（Clash 别名 `obfs`）保存 `type=obfs-local`、`mode=http|tls` 和可选 `host`。
- `v2ray-plugin` 保存 `type=v2ray-plugin`、`mode=websocket|quic`、可选 `host`、可选 `tls`；`path` 只用于 WebSocket。省略 mode 时保存 `websocket`。
- 未知插件或出现无法由上述对象表达的选项时，该 Node 记为 `unsupported`。
- 插件启用后 `network` 固定为 `tcp`；输入同时要求 UDP 时产生 warning，因为 SIP003 插件只承载 TCP。

### C.5 Hysteria2

| `config_json` 键 | 必要性与规则 |
|---|---|
| `password` | 必填 |
| `up_mbps`、`down_mbps` | 可选，存在时为正整数 |
| `obfs` | 可选对象；支持 `salamander`、`gecko`，启用时必须包含非空 `password` |
| `network` | 可选，`tcp`、`udp` 或省略表示两者 |
| `tls` | 必填且 `enabled=true` |

分享 URI 支持 `hysteria2://` 和 `hy2://`，userinfo 为 password；省略端口时使用标准默认值 443。`sni/peer`、`insecure/allowInsecure`、`alpn` 映射到 TLS；`up/up_mbps`、`down/down_mbps` 映射到带宽；`obfs-password/obfs_password` 映射到混淆密码。证书 pin、ECH 等无法无损映射的连接参数使该 Node 记为 `unsupported`，不能静默丢弃。

`hysteria://` 属于另一协议标识，不作为 Hysteria2 别名。端口跳跃、多端口和无法由 `address + port` 完整表达的输入在 V1.0 中记为 `unsupported`。

| 内部字段 | Hysteria2 URI | Clash YAML | 缺省值 |
|---|---|---|---|
| 名称、地址、端口 | Fragment、host、port | `name`、`server`、`port` | URI 端口缺省为 443 |
| `password` | userinfo | `password`、`auth` | 无；Clash 两者冲突时无效 |
| `up_mbps` | `up`、`up_mbps` | `up`、`up_mbps` | 省略 |
| `down_mbps` | `down`、`down_mbps` | `down`、`down_mbps` | 省略 |
| `obfs.type` | `obfs` | `obfs` | 省略 |
| `obfs.password` | `obfs-password`、`obfs_password` | `obfs-password` | obfs 启用时必填 |
| `obfs.min_packet_size` | 无 | `obfs-min-packet-size` | 仅 gecko，可选 |
| `obfs.max_packet_size` | 无 | `obfs-max-packet-size` | 仅 gecko，可选 |
| TLS Server Name | `sni`、`peer` | `sni`、`servername` | 省略 |
| TLS insecure | `insecure`、`allowInsecure` | `skip-cert-verify` | `false` |
| TLS ALPN | `alpn` | `alpn` | 省略 |

带宽文本接受正整数或带 `Mbps` 后缀的正整数，统一保存整数 Mbps；其他单位、零和负数无效。gecko 的 packet size 必须为正整数，两个值同时存在时最小值不得大于最大值。Clash 同时提供 `password` 和 `auth` 时，两者相同则取 `password`，不同则记为 `invalid`。

## 附录 D：Clash Proxy 映射补充

### D.1 公共字段映射

Clash 条目的 `name`、`type`、`server`、`port` 映射为标准 Node 公共字段。`type: ss` 映射为 `shadowsocks`，`type: hy2` 映射为 `hysteria2`。五种协议的其余常用字段按附录 B、C 的映射：

- `skip-cert-verify` → `tls.insecure`；
- `servername/sni`、`alpn`、`client-fingerprint` → TLS；
- `ws-opts`、`h2-opts`、`grpc-opts` → Transport；
- `reality-opts.public-key/short-id` → VLESS Reality；
- `cipher` → VMess security 或 Shadowsocks method；
- Hysteria2 的 `password/auth`、`up/down`、`obfs/obfs-password` → 对应协议参数。

顶层 `proxies` 中的每个条目独立解析。一个条目无效或不受支持不会阻止其他条目解析；条目中已知但无法表达的连接能力会使该条目跳过，普通未知字段只记录字段名警告。

Clash `fingerprint` 表示证书指纹，不能当作 uTLS `client-fingerprint`；当前数据契约无法无损保存时，该 Node 记为 `unsupported`。

### D.2 未映射字段分类

为了让独立实现得到相同结果，Clash Proxy 中未进入附录 B、C 映射表的字段按下表处理：

| 输入情况 | 处理 |
|---|---|
| `udp: true` | 接受并省略 `config.network` |
| `udp: false` | 接受并保存 `config.network=tcp` |
| `tfo`、`mptcp`、`interface-name`、`routing-mark`、`ip-version`、`prefer-ipv6`、`smux` | Node 仍可连接，忽略并按字段名记录 warning |
| 已知扩展对象未启用，或值为空 | 忽略并按字段名记录 warning |
| 未映射的 `*-opts`、TLS/Reality/Transport/插件扩展或其他会改变远端握手的字段 | 跳过 Node，记录 unsupported |
| 其他未知标量字段 | 忽略并按字段名记录 warning |
| `proxies` 之外的 Clash 顶层字段 | 不属于 Node 条目，直接忽略且不产生 warning |

warning 和 unsupported 消息只列字段名。解析器维护显式的已知字段集合，不通过字段值或异常文本推断是否敏感。

## 附录 E：稳定失败码

页面文案可以本地化，代码和测试按以下值判断：

| 类别 | `failure_code` |
|---|---|
| URL 不是合法 HTTPS | `invalid_subscription_url` |
| DNS、连接、TLS、超时或重定向失败 | `subscription_request_failed` |
| HTTP 状态不是 2xx | `subscription_http_error` |
| 响应体超过限制 | `subscription_too_large` |
| 响应不是 UTF-8 | `invalid_utf8` |
| 无法识别正文格式 | `unknown_format` |
| YAML/Base64 结构已经识别但内容破损 | `malformed_format` |
| 条目或 YAML 结构超过限制 | `resource_limit` |
| 没有合法 Node | `no_valid_nodes` |
| 合法 Node 名称重复 | `duplicate_name` |
| Filter/Exclude 后为空 | `filtered_empty` |

## 附录 F：格式依据

- [Shadowsocks SIP002 URI Scheme](https://github.com/shadowsocks/shadowsocks-org/wiki/SIP002-URI-Scheme)
- [Hysteria2 URI Scheme](https://v2.hysteria.network/docs/developers/URI-Scheme/)
