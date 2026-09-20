# ProxyHub V1.0 sing-box 集成设计

> 文档版本：v0.2
> 文档状态：待确认
> 更新日期：2026-09-20
> 需求基线：[ProxyHub V1.0 需求规范](01-requirements.md)
> 架构基线：[ProxyHub V1.0 软件架构设计](02-architecture.md)
> 数据基线：[ProxyHub V1.0 数据模型设计](03-data-model.md)
> 输入基线：[ProxyHub V1.0 Node 与 Subscription 输入解析设计](04-input-parsing.md)

本文定义数据库业务数据到 sing-box 运行配置的映射，以及配置文件、控制接口、子进程和二进制文件的集成方式。数据库是业务数据的权威来源；sing-box 配置和二进制是可替换的运行文件。

主要对应需求：REQ-GEN-003～004、REQ-CONFIG-001～005、REQ-CONFIG-013～021、REQ-OUTBOUND-007、REQ-RUNTIME-002～005、REQ-HEALTH-003、REQ-UPGRADE-001～003、REQ-REL-004。

第 1～7 章是主要设计，供整体方案评审；附录给出实现所需的精确字段映射、样例和验证清单。

## 1. 设计概览

### 1.1 集成边界

`app/singbox/` 是 ProxyHub 与 sing-box 的唯一集成边界，内部按职责拆分：

| 组件 | 职责 |
|---|---|
| 配置生成器 | 将调用方提供的一致数据库快照转换为完整配置对象；不访问数据库和文件 |
| 配置文件管理器 | 写入候选配置、调用配置检查、原子替换正式配置并保存最近一次成功运行配置 |
| Node 检测代理 | 通过内部 Mixed Inbound 将 HTTP 请求精确路由到指定 Node，返回真实状态码和延迟 |
| 控制接口客户端 | 查询 selector Current Node 和切换 selector |
| 子进程适配器 | 识别、启动、观察和停止 ProxyHub 管理的唯一 sing-box 进程 |
| 二进制管理器 | 读取版本、查询官方稳定版、下载、验证和原子替换 sing-box 二进制 |

集成层执行确定的转换和引擎操作，不决定管理状态、AUTO 候选顺序、故障切换目标、数据库事务或页面行为。调用方负责提供已经满足业务约束的数据快照和明确的操作目标。

### 1.2 主要处理路径

```text
一致数据库快照 + 内部检测凭据
  → 配置生成器
  → 同目录候选配置
  → sing-box check
  → 原子替换 data/config.json
  → 启动并等待控制接口就绪
  → 更新 data/config.last-success.json

Runtime 明确操作
  → Node 检测代理 / 控制接口客户端
  → URL test / 查询 selector / 切换 selector

官方 GitHub Release
  → 临时压缩包
  → 摘要、归档、架构、版本和配置兼容性验证
  → 原子替换 data/bin/sing-box
```

### 1.3 关键设计结论

| 主题 | 设计结论 |
|---|---|
| 配置来源 | 每次启动均读取最新数据库快照并生成完整配置，不增量修改旧配置 |
| 生成范围 | 全部合法 Node；仅 Routed Inbound 和 Routed MANUAL/AUTO；Route 引用时生成 DIRECT |
| selector | MANUAL 与 AUTO 使用相同的 sing-box selector；Default Node 是启动默认项 |
| priority | 不写入配置，也不决定 selector 成员顺序；成员按 Node ID 稳定排序 |
| 路由兜底 | 每条业务 Route 精确匹配一个 Inbound，末尾增加无条件 reject 规则 |
| Node 检测 | 内部 Mixed Inbound 按认证用户名把并发 HTTP 请求分别路由到目标 Node，并保留真实状态码 |
| 控制接口 | Clash API 仅监听 `127.0.0.1:9090`，用于 selector 查询与切换 |
| 配置生效 | `check` 成功才替换正式配置；进程就绪后才更新最近成功配置 |
| 进程识别 | PID 文件仅作线索，必须同时核对可执行文件和配置文件路径 |
| 版本基线 | V1.0 支持 sing-box `>=1.14.0,<2.0.0`；安装升级只取官方最新稳定版 |
| 下载校验 | 精确选择 `linux-amd64` 资产，并使用 GitHub Release API 返回的 SHA-256 digest 校验 |

最低版本选择 `1.14.0`，以覆盖本文使用的当前 Route Action、selector 控制和 Hysteria2 gecko 参数。版本低于最低值或主版本不是 `1` 时允许读取并展示版本，但不允许使用它检查配置或启动进程。

## 2. 完整配置生成

### 2.1 输入快照与纯生成

调用方在一次数据库读取范围内组装以下快照：

- `nodes`：全部 Node；
- `inbounds`：全部 Inbound；
- `outbounds`：全部 MANUAL/AUTO；
- `outbound_nodes`：全部 Node Pool 成员；
- `routes`：全部 Route。

配置生成器接收快照和调用方提供的内部检测密码。密码取应用认证密钥对 UTF-8 文本 `proxyhub/singbox-health-proxy/v1` 的 HMAC-SHA-256 十六进制结果，不增加用户设置；生成器不直接读取密钥。相同快照与相同密码必须生成语义和文本顺序稳定的配置。生成器不查询数据库、不读取既有 `config.json`、不调用网络，也不修改传入对象。

生成器再次检查协议字段、JSON 结构和引用完整性。发现未知协议、损坏 JSON、悬空引用、Default Node 不在 Pool、Pool 少于两个 Node、重复 tag 或监听控制端口冲突时，整个生成失败。不得跳过错误记录后生成部分配置。

### 2.2 生成范围

```text
routed_inbound_ids = routes.inbound_id
routed_outbound_ids = routes 中非 NULL 的 outbound_id

生成全部 Node Outbound
生成 routed_inbound_ids 对应的 Inbound
存在 Node 时生成内部 health-check Inbound
生成 routed_outbound_ids 对应的 selector
任一 Route 的 outbound_id 为 NULL 时生成 direct Outbound
按 Node ID 生成 health-check Route Rule
按 Route ID 生成全部 Route Rule
追加无条件 reject Rule
生成回环地址上的 Clash API
```

未被 Route 引用的业务 Inbound 和 MANUAL/AUTO 只保存在数据库中，不进入配置。Node 无论是否属于任何 Pool，都生成独立 Outbound，并在内部检测 Inbound 中具有对应用户，使运行时可以对任意 Node 执行 URL test。

### 2.3 Tag 规则

配置引用只使用数据库 ID，不使用可修改、可重名或包含特殊字符的展示名称。

| 对象 | Tag |
|---|---|
| Node | `node-{nodes.id}` |
| 业务 Inbound | `inbound-{inbounds.id}` |
| MANUAL/AUTO selector | `outbound-{outbounds.id}` |
| DIRECT | `direct` |
| 内部检测 Inbound | `health-check` |

这些 tag 同时用于 Route 和 Clash API。解析控制接口响应时必须按上述格式还原并核对 ID，不接受名称或其他 tag 作为业务对象。

### 2.4 顶层结构与顺序

生成文件只包含运行需要的顶层对象：

```text
log
inbounds
outbounds
route
experimental.clash_api
```

- `log.level` 为 `info`，`log.timestamp` 为 `true`；sing-box 标准输出和错误由进程适配器接入应用日志。
- V1.0 不生成独立 DNS 配置，域名解析使用 sing-box 和操作系统的默认行为。
- 数组按稳定规则输出：业务 Inbound 按 ID，其后为内部检测 Inbound；Node 按 ID、selector 按 ID；检测 Route 按 Node ID、业务 Route 按 Route ID。
- 不生成 `experimental.cache_file`，selector 的历史选择不会覆盖配置中的 Default Node。
- JSON 使用 UTF-8、两空格缩进并以换行结束。配置含有连接凭据，文件权限固定为 `0600`。

### 2.5 Node、selector 与 DIRECT

每个 Node 依据 `nodes.protocol`、公共字段和 `nodes.config_json` 生成一个协议 Outbound，精确映射见附录 A。

每个 Routed MANUAL/AUTO 生成一个 `selector`：

| 字段 | 取值 |
|---|---|
| `tag` | `outbound-{id}` |
| `outbounds` | Pool 中所有 `node-{node_id}`，按 Node ID 升序 |
| `default` | `node-{default_node_id}` |
| `interrupt_exist_connections` | `true` |

selector 成员不包含 `direct`。`priority` 只供 AUTO 决策使用，不改变生成内容；成员按 Node ID 排序用于保证输出稳定。`default` 显式指定，所以成员数组顺序不决定启动 Current Node。

MANUAL 与 AUTO 在 sing-box 中使用相同 selector。二者的区别由 Runtime 的业务控制决定，不写入 sing-box 配置。

只要存在 `outbound_id=NULL` 的 Route，就生成一次 `{type: direct, tag: direct}`；没有 DIRECT Route 时不生成。

### 2.6 Route

检测规则先按 Node ID 生成，其后每条业务 Route 生成一条当前格式的 Route Action：

```json
{
  "inbound": ["inbound-3"],
  "action": "route",
  "outbound": "outbound-7"
}
```

Route 指向 DIRECT 时，`outbound` 为 `direct`。数据库保证一个 Inbound 最多一条 Route；生成器仍检查重复引用并失败。

业务 Route 之后追加 `{ "action": "reject" }` 作为无条件兜底。这样意外流量不会落到 outbounds 数组第一项，也不需要已移除的 legacy block Outbound。所有已生成 Inbound 都有前置精确规则，正常业务流量不会进入兜底。

### 2.7 业务 Inbound

每个 Routed Inbound 使用 `inbound-{id}`、`listen_address`、`listen_port` 和 `inbounds.config_json` 生成。HTTP、SOCKS、Mixed、Shadowsocks、VMess 的具体输入契约和输出见附录 B。

两个内部端点固定占用 `127.0.0.1:9090` 和 `127.0.0.1:19090`。如果业务 Inbound 的监听范围覆盖任一端点，例如相同回环地址、相同端口的 IPv4 通配地址或双栈通配地址，配置生成失败并明确报告冲突对象。

### 2.8 Node 检测 Inbound

存在至少一个 Node 时，额外生成一个只监听 `127.0.0.1:19090` 的内部 Mixed Inbound，tag 为 `health-check`。它的 `users` 包含全部 Node：用户名为 `node-{id}`，密码为调用方提供的同一个派生密码。

每个 Node 在所有业务 Route 之前生成一条规则：

```json
{
  "inbound": ["health-check"],
  "auth_user": ["node-11"],
  "action": "route",
  "outbound": "node-11"
}
```

Inbound 与认证用户名共同限定路由，其他业务 Inbound 不受这些规则影响。不同 Node 使用不同用户名，因此多个检测请求可以并发经过同一监听端口，不需要切换共享 selector。没有 Node 时不生成该 Inbound 和检测规则。

派生密码只作为内部路由凭据，随生成配置以 `0600` 权限保存，不写日志或接口响应。内部端点只监听回环地址。

### 2.9 Clash API

配置固定生成：

```json
{
  "experimental": {
    "clash_api": {
      "external_controller": "127.0.0.1:9090",
      "secret": ""
    }
  }
}
```

该端点只允许 ProxyHub 本机访问，不生成 `external_ui`、CORS 或公网监听。V1.0 的单实例与固定数据目录保证同一时间只有一个 ProxyHub 使用这个内部端点。

### 2.10 生成伪代码

```text
build(snapshot):
    解析所有 config_json 并校验快照引用和跨对象不变量
    计算 Routed Inbound、Routed MANUAL/AUTO 和是否需要 DIRECT
    检查业务监听端点与两个内部端点

    inbounds = 按 ID 映射 Routed Inbound；有 Node 时追加 health-check
    node_outbounds = 按 ID 映射全部 Node
    selectors = 按 ID 映射 Routed MANUAL/AUTO
    direct = 存在 DIRECT Route 时加入一次
    rules = 按 Node ID 生成检测规则，按 Route ID 生成业务规则，再追加 reject

    返回完整配置对象
```

## 3. 配置文件与生效

### 3.1 文件约定

| 文件 | 用途 |
|---|---|
| `data/config.json` | 最近一次通过 `check` 并被用于启动尝试的正式配置 |
| `data/config.last-success.json` | 最近一次使 sing-box 成功就绪的配置，只用于排错 |
| `data/.config-*.tmp` | 单次生成的候选配置，完成或失败后清理 |

两个正式文件都属于生成产物，不能反向恢复业务数据。`config.last-success.json` 不参与自动启动或故障恢复；恢复时仍从最新数据库重新生成。

### 3.2 检查与替换

```text
生成配置对象
  → 在 data/ 中创建唯一候选文件，权限 0600
  → 写入、flush、fsync
  → data/bin/sing-box check -c <candidate>
  → 检查成功：os.replace(candidate, data/config.json)
  → fsync data/ 目录
```

配置检查最长 15 秒。非零退出、超时、无法执行或输出异常均为失败；错误结果保留退出码和最后 4 KiB 标准错误供日志使用，页面只显示简短原因。

生成或检查失败时删除候选文件，不修改 `config.json` 和 `config.last-success.json`，不启动进程，不修改数据库，也不尝试使用旧配置启动。

### 3.3 启动成功后的保存

正式配置替换后，子进程适配器启动 sing-box 并等待控制接口就绪：

- 进程在就绪前退出，启动失败；
- 10 秒内 `GET /proxies` 未得到合法响应，停止本次进程并判定启动失败；
- 控制接口就绪后，启动成功。

只有启动成功后，才把本次 `config.json` 内容以同样的临时写入和原子替换方式保存为 `config.last-success.json`。如果 `last-success` 更新失败，本次启动视为失败并停止进程，避免“成功运行配置”记录与事实不一致。

启动检查通过但进程启动失败时，新的 `config.json` 保留用于排错，旧的 `config.last-success.json` 保持不变。后续恢复仍重新读取数据库、生成和检查配置。

## 4. Node 检测与控制接口

### 4.1 URL test

Node 检测代理对 `https://` Test URL 发起 GET，并把 HTTP 代理设置为内部 Mixed Inbound：

```text
http://node-{id}:<derived-password>@127.0.0.1:19090
```

HTTP 客户端使用系统 CA 校验证书及主机名，不跟随重定向；从请求开始到取得响应头使用单调时钟计算毫秒延迟，取得响应头后立即关闭响应，不下载正文。只有 HTTP 2xx 为成功；3xx、4xx、5xx、代理认证失败、连接失败、TLS 失败和超时均返回失败原因。

HTTP 客户端总超时使用 Settings 的 URL Timeout。用户名、密码和完整 Test URL 不写日志。TCP 直连检测、两个检测结果的组合、健康状态保存和批量并发不属于 sing-box 集成层。

Clash API `/delay` 只返回延迟，不返回目标 HTTP 状态，因此不用于健康判定。

### 4.2 Clash API 请求约定

控制客户端只访问 `http://127.0.0.1:9090`。请求和响应体设大小上限，JSON 解码后校验字段类型；连接失败、超时、非预期状态码、非法 JSON 和业务字段不匹配分别返回明确失败原因。

| 操作 | 请求 | 成功判定 |
|---|---|---|
| 就绪检查 | `GET /proxies` | HTTP 200，响应含对象类型的 `proxies` |
| 查询 Current Node | `GET /proxies/{selector-tag}` | HTTP 200，`now` 是该 Pool 中的 Node tag |
| 切换 Current Node | `PUT /proxies/{selector-tag}`，JSON `{ "name": node-tag }` | HTTP 200/204，随后查询值等于目标 Node tag |

路径段使用标准 URL 编码，控制请求最长 5 秒。

### 4.3 查询与切换

查询 selector 后，客户端核对 `now` 是否属于该 selector 对应的 Pool；缺失、DIRECT、其他 selector 或未知 Node 均视为状态异常。

切换前，调用方给出 selector ID 和目标 Node ID；客户端核对 tag 形状，发送 PUT，再以 GET 复核。selector 配置中的 `interrupt_exist_connections=true` 负责中断使用旧 Node 的已有连接，无需调用全局连接删除接口。

控制客户端不更新数据库或 Runtime State。调用方只在“PUT 成功且 GET 复核一致”后提交相应业务状态；任一步失败时返回失败结果。

## 5. 子进程适配

### 5.1 进程标识

PID 文件为 `data/sing-box.pid`。PID 可能复用，因此读取 PID 后必须在 `/proc/{pid}` 同时核对：

- `/proc/{pid}/exe` 的真实路径等于 `data/bin/sing-box`；
- 命令行包含 `run -c`，配置参数的真实路径等于 `data/config.json`。

两项都匹配才是 ProxyHub 管理的 sing-box。PID 文件错误或过期时清理；ProxyHub 重启后可以扫描 `/proc` 找到此前遗留的精确匹配进程。该进程只用于安全停止，不直接接管为新的运行周期；应用启动必须先停止它，再按最新数据库重新生成、检查和启动。停止失败时不得创建第二个进程。不得按进程名终止其他 sing-box 实例。

### 5.2 启动

启动命令为：

```text
data/bin/sing-box run -c data/config.json
```

子进程使用独立进程组，工作目录和全部文件路径使用启动时确定的绝对路径。标准输出和标准错误进入受限缓冲并接入 ProxyHub 日志，不能因管道无人读取阻塞进程，也不能无限占用内存或磁盘。

启动后原子写入 PID 文件，再按第 3.3 节等待控制接口。同一 ProxyHub 运行周期内已有精确匹配进程时启动操作返回其状态，不创建第二个进程；应用重启发现的遗留进程按第 5.1 节先停止。存在疑似但身份不匹配的 PID 时不操作该进程。

### 5.3 停止与观察

停止仅针对经过身份核对的 PID：

1. 向其进程组发送 `SIGTERM`；
2. 最长等待 3 秒并轮询退出；
3. 仍未退出时发送 `SIGKILL`；
4. 确认 PID 已消失后清理 PID 文件和进程句柄。

停止失败时保留可观测状态并返回失败，不启动替代进程。子进程适配器提供 `get_pid`、`is_running`、`start`、`stop`、`check_config` 和有界错误尾部等基础操作；Restart 和管理状态转换由 Runtime 组合。

## 6. 二进制下载与升级

### 6.1 文件与状态

正式二进制固定为 `data/bin/sing-box`。不存在、不是普通文件、不可执行、版本命令失败或版本低于 `1.14.0` 时，不能用于配置检查或启动；页面分别显示“未安装”或检测到的版本及不可用原因。

远程版本检查、首次下载和升级只在调用方已经确认管理状态为 `stopped` 后执行，并与其他运行控制操作串行。成功后保持 `stopped`，不生成配置、不启动进程。

### 6.2 官方版本发现与资产选择

版本检查请求：

```text
GET https://api.github.com/repos/SagerNet/sing-box/releases/latest
Accept: application/vnd.github+json
User-Agent: ProxyHub/1.0
```

只接受非草稿、非 prerelease、主版本为 `1` 且不低于 `1.14.0` 的语义版本 tag `vMAJOR.MINOR.PATCH`。从 `assets` 精确选择：

```text
sing-box-{version}-linux-amd64.tar.gz
```

不模糊选择 `amd64v3`、`musl`、其他架构或其他归档。下载 URL 必须来自所选资产的 `browser_download_url`，摘要必须是同一资产的 `digest`，格式为 `sha256:` 加 64 位十六进制文本。缺少或格式非法时终止，不安装未经摘要验证的文件。

本地不存在时，兼容的最新稳定版视为可下载；本地版本较低时可升级；相同或更高版本不替换。官方 latest 已进入不兼容主版本时返回“暂无兼容更新”，不能自动安装。版本比较按语义版本数值进行，不按字符串比较，也不自动降级。

### 6.3 下载限制与摘要校验

Release JSON 最大 2 MiB、压缩包最大 256 MiB；先校验合法 `Content-Length`，下载时继续累计实际字节数。网络超时分别为版本查询 15 秒、文件下载 120 秒，流式块大小 64 KiB。

压缩包写入 `data/bin/.sing-box-upgrade-*/` 下的独占临时文件，写完执行 `flush` 和 `fsync`。随后计算 SHA-256，并与 GitHub API 中资产的 digest 作常量时间比较。大小超限、响应中断、摘要不一致或请求失败均清理临时目录并保留正式二进制。

### 6.4 安全解压与候选验证

归档最多检查 1024 个成员，只提取目录层级中的唯一普通文件 `sing-box`。以下情况均拒绝：

- 绝对路径、`..`、反斜杠、NUL 或无法规范化的成员名；
- symlink、hardlink、设备文件或其他特殊成员；
- 缺少二进制、出现多个候选或解压后超过 128 MiB。

候选文件设为 `0755`，按顺序验证：

1. ELF64、小端、`e_machine=62`，即 Linux x86-64；
2. 执行 `candidate version` 成功，解析到的版本与 Release tag 完全一致且不低于最低版本；
3. 使用候选二进制检查调用方准备的兼容性配置；数据库存在 Route 时从当前业务快照生成临时配置，否则使用内置最小配置；
4. 检查在超时内成功，候选仍为同一普通文件。

无 Route 时使用的最小配置固定为一个 `direct` Outbound 和一条无条件 `reject` Rule：

```json
{
  "outbounds": [{"type": "direct", "tag": "direct"}],
  "route": {"rules": [{"action": "reject"}]}
}
```

第三步用于发现新版本与 ProxyHub 当前生成格式不兼容的问题。候选输出和错误同样采用有界捕获。

### 6.5 原子替换与失败保护

候选与正式二进制位于同一文件系统。已有正式二进制时，先为其建立同目录唯一备份并 `fsync` 目录；备份失败则不替换。随后用 `os.replace` 原子替换 `data/bin/sing-box`，`fsync` 目录，并从正式路径再次核对版本。

替换后的核对或目录同步失败时，立即用备份原子恢复原二进制并再次同步目录；首次安装则删除失败的新文件。只有全部步骤成功后才删除备份。恢复失败属于严重错误，必须保留备份路径并明确记录，不能把新文件报告为安装成功。

任一步失败时返回阶段和安全错误摘要、记录详细日志并清理临时文件。不得留下半写的正式二进制，也不得因升级失败删除或改名原二进制。替换成功后重新执行正式路径的版本命令并返回结果。

## 7. 结果与错误边界

各组件返回简单、稳定的操作结果：

| 结果 | 主要字段 |
|---|---|
| 配置生成/检查 | `success`、`stage`、`message`、可选诊断尾部 |
| Node URL test | `success`、`message`、可选 `status_code/delay_ms` |
| 控制接口 | `success`、`operation`、`message`、可选 `current_node_id` |
| 进程操作 | `success`、`message`、`pid`、`running` |
| 版本检查 | `success`、`installed_version`、`latest_version`、`update_available` |
| 下载升级 | `success`、`stage`、`message`、可选 `installed_version` |

`message` 不包含 Node 密码、UUID、Subscription URL、完整配置、HTTP 响应正文或 GitHub 下载 query。页面使用简短消息，详细诊断写日志；无需建立大型异常层级。

## 附录 A：Node Outbound 映射

### A.1 公共字段

| 数据库输入 | sing-box Outbound |
|---|---|
| `protocol` | `type` |
| `id` | `tag=node-{id}` |
| `address` | `server` |
| `port` | `server_port` |
| `config_json.network` | 可选 `network` |

`network` 省略时不生成，表示使用协议默认能力；值为 `tcp` 或 `udp` 时原值写入。该字段与 V2Ray Transport 类型无关。

### A.2 TLS 与 Reality

数据库没有 `tls` 时不生成 Outbound `tls`。存在时映射：

| `config_json.tls` | Outbound `tls` |
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

Reality 只允许用于 VLESS。Trojan 和 Hysteria2 必须具有 `enabled=true` 的 TLS；违反时整个配置生成失败。

### A.3 V2Ray Transport

VMess、VLESS 和 Trojan 的 `transport` 映射：

| 数据库对象 | sing-box 对象 |
|---|---|
| `type=ws`、`path`、可选 `headers.Host` | WebSocket 同名字段 |
| `type=http`、`path`、可选 `host` | HTTP 同名字段 |
| `type=grpc`、可选 `service_name` | gRPC 同名字段 |

没有对象时不生成 `transport`。未知类型或不能完整表达的字段组合使配置生成失败，不能降级为普通 TCP。

### A.4 各协议

| 协议 | `nodes.config_json` | sing-box Outbound |
|---|---|---|
| VMess | `uuid`、`security`、`alter_id` | 同名字段 |
| VLESS | `uuid`、可选 `flow` | 同名字段 |
| Trojan | `password` | `password` |
| Shadowsocks | `method`、`password` | 同名字段 |
| Hysteria2 | `password`、可选 `up_mbps/down_mbps` | 同名字段 |

所有协议再应用适用的公共 `network`、TLS 和 Transport。

Shadowsocks 的结构化 `plugin` 映射为 `plugin` 与规范 `plugin_opts`：

- `obfs-local`：`obfs=<mode>`，可选追加 `;obfs-host=<host>`；
- `v2ray-plugin`：`mode=<mode>`，依次追加适用的 `;host=<host>`、`;path=<path>`、`;tls`。

生成器只处理 04 输入契约接受的插件和值；无法无损序列化的选项使配置生成失败。

Hysteria2 的 `obfs` 对象原结构映射为 Outbound `obfs`，包括 `type`、`password`，以及 gecko 可选的 `min_packet_size`、`max_packet_size`。

## 附录 B：Inbound 输入契约与映射

### B.1 公共规则

`inbounds.config_json` 必须是 JSON 对象。所有 Inbound 输出：

| 数据库字段 | sing-box Inbound |
|---|---|
| `protocol` | `type` |
| `id` | `tag=inbound-{id}` |
| `listen_address` | `listen` |
| `listen_port` | `listen_port` |

未知键、缺少必填键、错误 JSON 类型和不支持的枚举值均使完整配置生成失败。V1.0 不在 Inbound 中生成 TLS、multiplex 或 sniff 等附加能力。

### B.2 HTTP、SOCKS 与 Mixed

三种协议使用相同的认证对象：

```json
{}
```

表示不启用认证；或：

```json
{"username": "proxy", "password": "secret"}
```

表示生成单项 `users`。用户名和密码必须同时为非空字符串，不允许只提供其中一项。Mixed 同时接受 HTTP 与 SOCKS 客户端，认证规则相同。

### B.3 Shadowsocks

```json
{"method": "2022-blake3-aes-128-gcm", "password": "MDEyMzQ1Njc4OWFiY2RlZg=="}
```

`method` 和 `password` 必填并直接生成同名字段。方法范围为 sing-box 1.14 Shadowsocks Inbound 支持的 2022、AEAD 与 `none` 方法；不接受仅能作为旧式 Outbound 使用的方法。密码还必须满足所选 2022 方法的密钥格式要求，最终由 `sing-box check` 复核。

### B.4 VMess

```json
{"uuid": "8e600429-f5ba-495e-b0a6-d8fbc9ec878b", "alter_id": 0}
```

`uuid` 必须是规范 UUID；`alter_id` 缺省为 `0`，必须是非负整数。输出为单项 `users`，字段分别是 `uuid` 和 sing-box 使用的 `alterId`。

## 附录 C：完整配置样例

以下快照包含一个 Routed Mixed、一个 Routed MANUAL、两个 Node 和一条 Route：

```text
Inbound #3: mixed, 127.0.0.1:1080, config_json={}
Node #11: shadowsocks
Node #12: vmess
MANUAL #7: members=[11,12], default_node_id=12
Route #5: inbound_id=3, outbound_id=7
```

生成结构的关键部分为：

```json
{
  "log": {"level": "info", "timestamp": true},
  "inbounds": [
    {
      "type": "mixed",
      "tag": "inbound-3",
      "listen": "127.0.0.1",
      "listen_port": 1080
    },
    {
      "type": "mixed",
      "tag": "health-check",
      "listen": "127.0.0.1",
      "listen_port": 19090,
      "users": [
        {"username": "node-11", "password": "sanitized-derived-password"},
        {"username": "node-12", "password": "sanitized-derived-password"}
      ]
    }
  ],
  "outbounds": [
    {
      "type": "shadowsocks",
      "tag": "node-11",
      "server": "ss.example.invalid",
      "server_port": 443,
      "method": "aes-256-gcm",
      "password": "sanitized-password"
    },
    {
      "type": "vmess",
      "tag": "node-12",
      "server": "vmess.example.invalid",
      "server_port": 443,
      "uuid": "8e600429-f5ba-495e-b0a6-d8fbc9ec878b",
      "security": "auto",
      "alter_id": 0
    },
    {
      "type": "selector",
      "tag": "outbound-7",
      "outbounds": ["node-11", "node-12"],
      "default": "node-12",
      "interrupt_exist_connections": true
    }
  ],
  "route": {
    "rules": [
      {
        "inbound": ["health-check"],
        "auth_user": ["node-11"],
        "action": "route",
        "outbound": "node-11"
      },
      {
        "inbound": ["health-check"],
        "auth_user": ["node-12"],
        "action": "route",
        "outbound": "node-12"
      },
      {
        "inbound": ["inbound-3"],
        "action": "route",
        "outbound": "outbound-7"
      },
      {"action": "reject"}
    ]
  },
  "experimental": {
    "clash_api": {
      "external_controller": "127.0.0.1:9090",
      "secret": ""
    }
  }
}
```

样例中的域名和凭据均为无效脱敏值，用于检查结构和 `sing-box check`，不用于连通性验证。

## 附录 D：实现与验证清单

### D.1 配置生成单元样例

至少覆盖：

- 五种 Node 及 TLS、Reality、三种 Transport、两种 Shadowsocks plugin、Hysteria2 两种 obfs；
- 五种 Inbound、无认证和单用户认证；
- DIRECT、MANUAL、AUTO，以及同一 selector 被多条 Route 引用；
- 内部 Mixed Inbound 的用户与每个 Node 一一对应，`auth_user` 规则在业务 Route 之前；
- 未 Routed 对象不生成、全部 Node 始终生成、priority 改变不影响输出；
- Default Node 决定 selector `default`，成员顺序按 Node ID；
- 悬空引用、坏 JSON、Pool 少于两个 Node、重复 Route 和两个内部端口冲突整体失败；
- 每种成功配置均通过目标版本 `sing-box check`。

### D.2 文件与进程集成样例

- 配置生成失败和 `check` 失败时两个正式配置不变；
- `check` 成功后原子替换 `config.json`；仅进程就绪后更新 `config.last-success.json`；
- 进程立即退出、控制接口未就绪、停止超时和过期 PID 文件；
- ProxyHub 重启后只识别并停止可执行路径与配置路径都匹配的遗留进程，再生成配置开始新运行周期；
- MANUAL/AUTO 查询和切换，切换后 `now` 与目标一致；
- URL test 的 2xx 成功、3xx/4xx/5xx、TLS、代理认证和超时失败；非法控制响应。

### D.3 二进制管理样例

- 未安装、已是最新版、存在升级和本地版本异常；
- Release JSON、资产名、digest、Content-Length 和语义版本异常；
- 下载中断、大小超限、SHA-256 不一致；
- 路径穿越、链接、特殊文件、多个二进制、错误 ELF 架构；
- 版本不一致、候选配置检查失败、原子替换失败；
- 每种失败都保留原二进制，成功后版本正确且管理状态仍为 `stopped`。

### D.4 本设计形成时的验证基线

- 工作区现有二进制为 sing-box `1.13.19 linux/amd64`，可执行 `version` 和现有配置检查，但低于本设计最低版本；
- 2026-09-20 查询官方 latest release 得到 `v1.14.1`；其 `linux-amd64.tar.gz` 资产提供 `sha256:` digest，没有独立 checksum 资产，因此实现以 Release API 的资产 digest 为完整性依据；
- 旧分支中的下载、受限读取、安全解压、进程身份核对和原子替换方式可复用；旧的 DIRECT 哨兵行、生成全部 selector、selector 追加 DIRECT、legacy block Outbound 和旧 Route 字段不可沿用。

## 附录 E：设计依据

- [sing-box 配置结构](https://sing-box.sagernet.org/configuration/)
- [Route Rule](https://sing-box.sagernet.org/configuration/route/rule/)
- [Route Rule Action](https://sing-box.sagernet.org/configuration/route/rule_action/)
- [Selector Outbound](https://sing-box.sagernet.org/configuration/outbound/selector/)
- [Direct Outbound](https://sing-box.sagernet.org/configuration/outbound/direct/)
- [Clash API](https://sing-box.sagernet.org/configuration/experimental/clash-api/)
- [sing-box 1.14.1 URL test 实现](https://github.com/SagerNet/sing-box/blob/v1.14.1/common/urltest/urltest.go)
- [HTTP Inbound](https://sing-box.sagernet.org/configuration/inbound/http/)
- [SOCKS Inbound](https://sing-box.sagernet.org/configuration/inbound/socks/)
- [Mixed Inbound](https://sing-box.sagernet.org/configuration/inbound/mixed/)
- [Shadowsocks Inbound](https://sing-box.sagernet.org/configuration/inbound/shadowsocks/)
- [VMess Inbound](https://sing-box.sagernet.org/configuration/inbound/vmess/)
- [VMess Outbound](https://sing-box.sagernet.org/configuration/outbound/vmess/)
- [VLESS Outbound](https://sing-box.sagernet.org/configuration/outbound/vless/)
- [Trojan Outbound](https://sing-box.sagernet.org/configuration/outbound/trojan/)
- [Shadowsocks Outbound](https://sing-box.sagernet.org/configuration/outbound/shadowsocks/)
- [Hysteria2 Outbound](https://sing-box.sagernet.org/configuration/outbound/hysteria2/)
- [TLS Fields](https://sing-box.sagernet.org/configuration/shared/tls/)
- [V2Ray Transport](https://sing-box.sagernet.org/configuration/shared/v2ray-transport/)
- [SagerNet/sing-box Releases](https://github.com/SagerNet/sing-box/releases)
