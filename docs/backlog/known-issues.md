# ProxyHub v2 — 已知问题与后端优化清单

> 建立日期：2026-08-24
> 最近复核：2026-08-25
> 复核范围：除前端页面、`templates/`、`static/` 和 `app/web/` 外的全部后端代码、运行入口与部署文件。
> 当前状态：静态扫描完成；尚未开始修复。完成修复后，应在对应条目下补充提交号和验证结果。

## 1. 当前结论

当前后端采用 Flask + SQLite + sing-box 的模块化单体结构，技术选型和一级目录边界总体合理：

- `parser/` 负责不可信订阅内容到内部节点模型的转换；
- `db/` 负责 SQLite 持久化；
- `singbox/` 负责配置翻译、进程、Clash API 和升级适配；
- `services/` 负责业务编排；
- `web/` 负责 HTTP 请求与响应适配。

目前没有必要引入 ORM、消息队列、微服务或大型前端框架。主要结构问题是 sing-box 生命周期控制分散在 `services/runtime.py`、`services/checker.py` 和 `singbox/process.py`，缺少统一锁、配置版本、校验、就绪探测和失败回滚。这一问题同时导致 KI-006、KI-013、KI-019、KI-021 等运行时缺陷。

当前项目状态仍应定义为：**可试用，尚未达到稳定可用**。正式使用前至少应完成全部 P1，并在真实部署环境验证真实代理流量、进程切换和失败回滚。

## 2. 优先级定义

| 优先级 | 含义 |
|---|---|
| P1 | 可能造成核心功能失效、错误路由、节点数据丢失、错误进程操作或主机文件安全问题；正式使用前必须修复 |
| P2 | 功能语义不完整、错误处理不足、并发一致性或长期运行风险；P1 稳定后尽快修复 |
| P3 | 工程质量、部署、文档和维护性优化；不直接阻断当前手动流程 |

## 3. P1 — 正式使用前必须修复

### KI-001：空出口池仍生成指向不存在 selector 的路由

- 位置：`app/singbox/config.py::_build_selectors`、`_build_route`
- 现状：空出口池会跳过 `g{id}` selector，但路由只检查出口记录是否存在，仍把入口指向 `g{id}`。
- 影响：配置可能通过语法检查，但实际流量没有有效出口。
- 修改建议：让 `_build_selectors` 返回已生成 selector 集合；`_build_route` 只引用实际生成的 selector。产品语义统一为“拒绝启动”“回落 direct”或“跳过规则”，推荐拒绝启动并列出空池服务，避免静默直连。
- 验收：空池服务不得生成悬空 tag；启动返回明确错误，原运行配置不受影响。

### KI-002：服务 Stop 的目标 `direct` 不在 selector 成员中

- 位置：`app/singbox/config.py::_build_selectors`、`app/services/routing.py::stop_service`
- 现状：selector 只包含 `n{id}`，Stop 却切换到 `direct`。
- 影响：Clash API 可能拒绝切换，页面无法停止单个服务。
- 修改建议：若 Stop 表示直连，加入 `direct`；若表示阻断，加入 `block`，并统一状态文字和默认节点语义。
- 验收：服务可在池节点和停止目标之间往返切换，Clash API 的 `now` 与业务状态一致。

### KI-004：订阅解析为 0 时直接清空旧节点

- 位置：`app/services/subscriptions.py::refresh_subscription`
- 现状：正文为空、格式误判、登录页、限流页或不支持格式都会清空旧节点并级联删除出口池关联。
- 影响：一次异常响应即可破坏现有代理出口配置。
- 修改建议：默认将 0 节点视为刷新失败；仅在明确识别为合法空订阅或用户确认时允许清空；保存解析统计；节点 diff 与订阅元数据放入同一事务。
- 验收：HTML、空正文、未知格式、格式错误和过滤后为 0 时，旧节点及池关联保持不变。

### KI-013：节点测速无条件重启正在运行的 sing-box

- 位置：`app/services/checker.py::_ensure_singbox_with_nodes`、`app/services/runtime.py::apply_config`
- 现状：只要 sing-box 已运行，测速前都会写配置并 restart。
- 影响：连续或并发测速中断全部现有代理连接。
- 修改建议：计算规范化配置 hash，记录当前进程成功加载的 hash；配置不变时直接测速，变化时在统一运行时锁内校验并只重启一次。
- 验收：配置不变时连续和并发测速 PID 保持不变；配置变化后只重启一次。

### KI-014：升级压缩包存在目录穿越和任意文件写入

- 位置：`app/singbox/upgrade.py::_strip_root`、`_extract_zip`、`_extract_tar`
- 现状：成员名未经边界校验，`bundle/../../outside`、`bundle//tmp/outside` 可逃逸 `data/bin`。
- 影响：恶意或被篡改的发布包可覆盖应用权限范围内任意文件。
- 修改建议：拒绝绝对路径、`..`、设备文件、链接和非普通文件；用 `realpath/commonpath` 校验 staging 边界；只提取白名单文件；验证完成后原子替换二进制。
- 验收：ZIP/TAR 的父目录、绝对路径、符号链接和硬链接成员均被拒绝，目标目录外无变化。

### KI-015：订阅 HTTPS 关闭证书验证

- 位置：`app/services/subscriptions.py::fetch_subscription`
- 现状：显式设置 `check_hostname=False` 和 `CERT_NONE`。
- 影响：中间人可篡改订阅、注入节点或触发 KI-004 删除旧数据。
- 修改建议：默认使用系统 CA 和主机名验证；私有证书使用按订阅配置的显式高风险开关或自定义 CA，不允许全局静默关闭。
- 验收：过期、主机名不匹配和未知 CA 默认失败且保留旧节点；自定义 CA 有独立测试。

### KI-016：订阅格式识别不完整，可将有效订阅误判为 0 节点

- 位置：`app/services/subscriptions.py::decode_body`、`app/parser/base.py::decode_base64`、`app/parser/__init__.py::_looks_like_clash_yaml`
- 已确认：纯 Trojan/Hysteria2/TUIC 的 Base64 订阅不会解包；`proxies:` 位于前 512 字节之后的 Clash YAML 被当成 URI；service 和 parser 重复实现 Base64 规则。
- 修改建议：只保留一个解码/格式探测入口；支持全部已声明协议；安全解析并验证 YAML 顶层 `proxies`，不依赖固定长度启发式。
- 验收：各支持协议的纯 Base64、长注释 Clash YAML、BOM/空白订阅均正确识别；未知正文返回明确格式错误。

### KI-017：解析器缺少逐节点隔离和完整字段校验

- 位置：`app/parser/clash.py::parse_yaml`、各协议 parser、`app/singbox/protocol.py`
- 现状：一个非法 `alterId` 可让整批解析抛异常；空地址、端口 0、空 UUID/密码等仍可能入库；非法 JSON 退化为空配置。
- 影响：一个坏节点可阻断刷新，或让完整 sing-box 配置失效。
- 修改建议：Clash 节点逐项隔离；建立统一规范化节点模型和按协议 validator；区分坏节点、不支持节点和订阅整体无效；有效数量低于保护阈值时拒绝 diff。
- 验收：混合好坏节点时保留有效节点并报告错误计数；必填字段和端口范围都有测试。

### KI-018：Reality、uTLS fingerprint 等参数被解析后丢弃

- 位置：`app/parser/clash.py::_parse_vless`、`_parse_vmess`、`app/parser/vless.py`、`app/singbox/protocol.py::_apply_tls`
- 现状：parser 保存 Reality 和 fingerprint 字段，builder 只输出基础 TLS、SNI、insecure 和 ALPN。
- 影响：Reality 节点看似导入成功但无法连接；fingerprint 被静默忽略。
- 修改建议：建立到 sing-box TLS `reality`/`utls` 的显式映射；不支持字段必须 warning；补齐 VMess URI 的 SNI 等字段。
- 验收：Reality、普通 TLS、uTLS、WS、HTTP/2、gRPC 组合均通过 `sing-box check` 和真实连接测试。

### KI-019：新配置在校验前覆盖旧配置，启动失败没有回滚

- 位置：`app/services/runtime.py`、`app/singbox/config.py::write_config`
- 现状：先覆盖正式配置再停止/启动；没有 `sing-box check`、加载版本记录和失败回滚。
- 影响：坏数据会停止原本正常的代理并留下坏配置。
- 修改建议：写唯一临时文件，先 check；记录旧配置/hash；校验成功后原子切换；新进程未就绪时恢复旧配置和旧进程。
- 验收：无效节点、端口冲突、控制端口冲突和晚退出时，旧流量继续工作或自动恢复。

### KI-020：sing-box 进程识别和停止结果不可靠

- 位置：`app/singbox/process.py::_find_pid`、`restart`、`app/services/runtime.py::stop_singbox`
- 现状：只按二进制名和配置 basename 扫描；多个实例常都叫 `config.json`。restart 忽略 stop 失败，service 层总返回 `running=False`。
- 影响：可能操作错误实例、未加载新配置却报告成功，或进程仍在但显示停止。
- 修改建议：由运行时管理器持有 `Popen`/PID 文件；校验完整可执行文件和配置路径；stop 失败必须终止 restart 并重新探测真实状态。
- 验收：两个实例并存时只操作本实例；停止失败时准确返回失败和真实 running 状态。

## 4. P2 — 功能与长期运行风险

### KI-005：`auto_start` 只保存，不执行

- 位置：`app/db/service.py::get_auto_start_services`、启动流程
- 修改建议：先定义它表示启动进程还是控制 selector，再由统一运行时协调器执行；失败不阻塞 Web 启动。
- 验收：重启后只有标记服务进入约定状态，失败原因可查询。

### KI-006：启动只检查 0.2 秒存活，不等待控制面就绪

- 位置：`app/singbox/process.py::start`
- 修改建议：与 KI-019 一并处理：启动前 check，启动后轮询进程和 Clash API；超时收集有限 stderr、清理并回滚。
- 验收：成功响应后 Clash API 可立即使用；晚退出、端口占用和控制面未就绪均返回失败。

### KI-007：Web 端口和 `PROXYHUB_HOME` 语义不一致

- 位置：`run.py`、`app/config.py`、`app/settings.py`、部署文档
- 修改建议：启动时读取并校验 `web_port`；支持明确的环境变量路径覆盖或删除文档承诺；避免多 app 修改全局路径。
- 验收：端口设置重启后生效；路径覆盖后全部运行文件落入目标目录。

### KI-008：后端边界缺少统一参数校验和错误模型

- 位置：`app/web/api/*`、`app/db/*`、`app/services/*`
- 说明：本次未重新扫描 `app/web/`，但 DB/service 仍接受大量未验证字段，因此继续保留。
- 修改建议：统一 4xx JSON 错误；Web 校验类型、范围、协议和必填字段；service/DB 保留关键不变量防护。
- 验收：缺字段、非法协议、端口冲突、无效外键和重复关联返回一致 4xx，不出现 HTML 500。

### KI-011：核心业务没有自动化测试基线

- 现状：当前没有 `test/` 或 `tests/`；`unittest discover` 实际运行 0 项并返回成功。
- 修改建议：恢复 `tests/unit/` 和 `tests/integration/`；注入临时路径、SQLite、假 HTTP/Clash API/进程；默认无网络且不写真实 `data/`。
- 验收：CI 报告测试数量，0 tests 必须失败，优先覆盖全部 P1。

### KI-021：运行时操作没有统一协调器和并发锁

- 位置：`services/runtime.py`、`services/checker.py`、`singbox/process.py`、`singbox/upgrade.py`
- 现状：启动、停止、重启、测速、配置写入和升级可并发；固定 `config.json.tmp` 会互相覆盖。
- 修改建议：增加 `RuntimeManager`，所有状态变更经同一互斥锁；维护 desired hash、loaded hash、PID 和状态机；使用唯一临时文件。
- 验收：并发 start/restart/check/upgrade 不产生重复进程、部分配置或错误状态。

### KI-022：设置存储和会话密钥初始化存在并发风险

- 位置：`app/settings.py`、`app/__init__.py::_load_secret_key`
- 现状：全局内存 dict 和固定 `.tmp` 会导致丢更新；首次多 worker 启动可能生成不同 secret。
- 修改建议：设置写入加锁和唯一临时文件；secret 使用 `O_EXCL`/文件锁，或生产环境要求 `PROXYHUB_SECRET`。
- 验收：并发设置更新不丢失；首次并行启动的 worker 使用同一 secret。

### KI-023：数据库约束、事务边界和 WAL 生命周期不足

- 位置：`app/db/database.py`、`app/db/outbound.py`、`app/db/subscription.py`
- 现状：缺少池成员唯一约束、端口范围/冲突、入口唯一路由等不变量；订阅 diff 和元数据分开提交；每次 teardown 都执行 `wal_checkpoint(TRUNCATE)`。
- 修改建议：增加 UNIQUE/CHECK/索引；由 service 定义事务；订阅刷新加锁；普通 teardown 只关闭连接。
- 验收：重复成员、端口冲突、重复入口服务被拒绝；失败刷新完整回滚；并发请求无明显 checkpoint 争用。

### KI-024：服务状态把控制面故障误报为已停止

- 位置：`app/singbox/clash.py::get_proxy_now`、`app/services/routing.py::get_service_status`
- 现状：group 不存在、HTTP 错误、JSON 错误和不可达都返回 `None`，随后统一映射为 stopped。
- 修改建议：Clash client 返回 reachable、status、error、value；区分 running、stopped、missing、unreachable、unknown。
- 验收：关闭进程、删除 selector、API 500 时分别显示准确状态。

### KI-025：升级缺少完整性、原子替换和失败清理

- 位置：`app/singbox/upgrade.py`
- 现状：版本只做字符串不等比较；下载整体读内存；未验证 checksum、架构、版本和可执行性；异常可能残留临时文件；未与运行时锁协调。
- 修改建议：语义版本比较；限制大小并流式下载；验证官方 checksum；在 staging 执行 version/check；备份后原子替换，失败回滚。
- 验收：损坏包、错误架构、版本倒退、校验失败和中断均不破坏现有二进制。

### KI-026：订阅响应和解析缺少资源与目标限制

- 位置：`app/services/subscriptions.py`、`app/parser/clash.py`
- 现状：响应一次性读内存，无正文大小、节点数、YAML 复杂度限制；订阅 URL 可访问任意目标。
- 修改建议：仅允许 HTTP/HTTPS；按威胁模型限制 loopback、链路本地和内网；限制正文、节点数、解析耗时、重定向和 Content-Type。
- 验收：超大正文、重定向循环、受限目标和高复杂度 YAML 被拒绝，旧数据保持不变。

### KI-027：日志和运行数据可能泄露代理凭据

- 位置：`app/parser/__init__.py`、setting、SQLite、订阅 URL、日志目录
- 现状：解析失败日志包含 URI 前 60 字符；订阅 token、节点密码和 Web 密码明文保存；目录权限没有集中检查。
- 修改建议：日志只记录协议、订阅 id、节点序号和异常类型；启动时检查 data/log/secret 权限；文档明确备份安全边界。
- 验收：日志不含 token、密码或完整 URI；权限不安全时启动告警。

### KI-028：内存检查任务和延迟结果没有生命周期

- 位置：`app/services/checker.py::_tasks`、`_latencies`
- 现状：任务永久保留，节点删除后延迟残留；多 worker 状态不一致。
- 修改建议：增加 TTL、容量上限和节点删除清理；当前保持单 worker，多 worker 时再评估共享存储。
- 验收：长期测速后任务数量有界；删除节点后缓存消失。

### KI-030：运行路径使用进程全局可变模块状态

- 位置：`app/config.py::configure`
- 现状：创建第二个 app 会重设整个进程路径；并行测试或多实例可能访问错误 DB、配置和日志。
- 修改建议：短期明确单 app/单 worker；中期改为不可变配置对象，由 runtime/db 工厂持有。
- 验收：两个隔离 app 的 DB、配置、设置和日志完全互不影响。

## 5. P3 — 工程、部署与维护性优化

### KI-012：依赖和持续集成基线不足

- 现状：Flask、PyYAML 未固定版本；未声明 Python 范围、测试工具、格式化、静态检查和 CI。
- 修改建议：固定兼容范围并生成锁文件；增加 compile、lint、unit、integration、漏洞扫描和配置 check。
- 验收：干净环境可重复安装；CI 中 0 tests 失败；依赖升级有测试验证。

### KI-029：订阅解码、节点模型和协议映射存在重复规则

- 位置：`services/subscriptions.py`、`parser/base.py`、`parser/*`、`singbox/protocol.py`
- 现状：Base64 重复实现；parser 输出自由 dict，protocol 再解释同一批字符串字段，缺少单一 schema。
- 修改建议：引入轻量 dataclass/TypedDict 和统一规范化层；service 只 fetch/apply，parser 只 decode/parse，protocol 只接收已验证模型。
- 验收：每个协议字段有单一来源、类型定义和 parser→builder 契约测试。

### KI-031：部署仍偏开发模式

- 位置：`Dockerfile`、`docker-compose.yml`、`run.py`、`setup.sh`
- 现状：镜像不含应用代码，依赖整个仓库挂载；使用 Flask 开发服务器；端口固定；setup 提示运行不存在的 `start.sh`。
- 修改建议：稳定后构建自包含镜像，只挂载 data/logs；使用受控单 worker WSGI 或先验证多 worker；增加 healthcheck；修正 setup 提示。
- 验收：镜像无需源码挂载即可启动；健康检查区分 Web 存活和 sing-box 状态。

### KI-032：文档状态与当前代码和测试基线不一致

- 现状：旧文档仍引用已删除的 `test/`、旧 `app/services.py` 和“112 tests passed”。
- 修改建议：修复时同步本清单；区分当前架构、运维说明和历史设计；旧文档标记 archived/obsolete。
- 验收：仓库不再包含误导性的当前路径和测试数量；README 指向唯一有效文档。

## 6. 历史条目状态

### KI-003：2026-08-24 运行时数据没有节点和出口池成员

- 类型：历史部署数据快照，不是代码缺陷。本次不重新确认生产数据库。
- 后续：完成 KI-004、016、017、018 后，备份数据库并重新刷新，再验证池成员和真实流量。

### KI-009：配置测试会写入真实运行路径

- 状态：旧测试目录已删除，原破坏路径不存在；不再作为开放缺陷。
- 后续：恢复测试时必须使用临时目录，要求已并入 KI-011。

### KI-010：测试混合单元、手工冒烟和破坏性升级脚本

- 状态：旧测试目录删除，混放问题消失，但演变为 0 项自动测试。
- 后续：新测试分层和安全要求已并入 KI-011，不恢复旧结构。

## 7. 推荐实施批次

### 批次 A：安全测试底座

1. KI-011：建立临时路径、SQLite、假 HTTP/Clash API/进程夹具。
2. 为全部 P1 建立失败复现测试。
3. CI 强制测试数大于 0，默认测试不访问网络或真实 `data/`。

### 批次 B：数据和主机安全

1. KI-014、025：安全升级、staging 和回滚。
2. KI-015、026、027：安全订阅、资源限制和日志脱敏。
3. KI-004、016、017、018：格式识别、零节点保护、字段校验和协议完整性。

### 批次 C：统一 sing-box 运行时

1. KI-021：实现单一协调器和状态机。
2. KI-019、006、020：check、原子配置、就绪探测、进程身份和回滚。
3. KI-001、002、013、024：路由、停止语义、无扰测速和准确状态。

### 批次 D：一致性和功能语义

1. KI-023：约束、索引、事务和并发刷新。
2. KI-005、007、008、022、030：auto-start、路径/端口、校验和配置并发。
3. KI-028：缓存生命周期。

### 批次 E：工程和部署收尾

1. KI-012、029：依赖锁定、CI、类型契约和职责收敛。
2. KI-031、032：部署、healthcheck 和文档同步。

## 8. 本次扫描验证记录

| 检查 | 结果 |
|---|---|
| `python3 -m compileall -q app run.py` | 通过 |
| `python3 -m unittest discover -v` | 返回成功，但实际运行 0 项测试 |
| sing-box 版本 | 1.13.19 linux/amd64 |
| 当前 `data/config.json` 的 `sing-box check` | 通过；只代表语法有效，不代表真实节点、Reality 或路由语义正确 |
| Base64 包装的纯 Trojan 订阅 | 已复现解析为 0 节点 |
| `proxies:` 位于 512 字节后的 Clash YAML | 已复现解析为 0 节点 |
| Clash 中非法 `alterId` | 已复现整批抛出 `ValueError` |
| 空出口池 selector/route | 已复现 selector 缺失但 route 仍引用 `g{id}` |
| ZIP/TAR 路径规范化 | 已复现 `../` 和绝对路径可逃逸目标目录 |
| Ruff/Bandit | 当前环境未安装，待 KI-012 补入基线 |

## 9. 稳定可用的完成定义

全部 P1 完成后，还必须在真实 Docker/主机环境完成：

1. 订阅失败保护、节点 diff 和池关联保持测试；
2. 配置 check、启停、重启、控制面就绪和失败回滚；
3. selector 在节点与 direct/block 间切换的状态一致性；
4. 连续及并发测速的 PID 稳定性；
5. HTTP、SOCKS、SS、VMess 入站真实流量；
6. VMess、VLESS Reality、Trojan、SS、Hysteria2、TUIC 真实出口；
7. 升级成功、校验失败、提取失败和回滚；
8. 数据库与 `data/` 备份恢复演练。
