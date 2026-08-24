# ProxyHub v2 — 已知问题与后续优化清单

> 建立日期：2026-08-24
> 范围：基于当前 `singbox-rewrite` 分支的静态审查、隔离 API 冒烟测试、单元测试和 sing-box 配置检查。
> 目的：记录问题，不在本轮修改业务代码。完成修复后应在对应条目下补充提交号和验证结果。

## 1. 当前结论

订阅、节点、入口、出口和服务（路由）的手动 CRUD 链路已经形成；隔离环境中的“创建订阅 → 刷新节点 → 创建入口 → 创建出口池 → 创建服务”冒烟测试通过。现有 112 个可发现的单元测试通过，生成的完整样例配置可通过 sing-box 1.13.19 的 `check`。

目前仍有会影响真实代理流量的配置逻辑问题，因此项目状态应定义为：**可试用，尚未达到稳定可用**。

## 2. 优先级定义

| 优先级 | 含义 |
|---|---|
| P1 | 会导致核心手动功能失效、错误路由或运行时数据受损；正式使用前应修复 |
| P2 | 功能语义不完整、错误处理不足或长期运行风险；基础功能稳定后尽快修复 |
| P3 | 工程质量、部署和维护性优化；不直接阻断当前手动流程 |

## 3. 功能与运行时问题

### KI-001（P1）空出口池仍会生成指向不存在 selector 的路由

- 位置：`app/singbox/config.py::_build_selectors`、`_build_route`
- 现状：出口池为空时跳过 `g{id}` selector，但 `_build_route` 只检查出口记录是否存在，仍把入口路由到 `g{id}`。
- 影响：sing-box 配置可能通过语法检查并启动，但该入口的实际流量没有有效出口。
- 建议：生成路由时使用“已成功生成的 selector id 集合”；空池服务应明确回落到 `direct`、跳过规则或拒绝启动，三者需先确定产品语义。
- 验收：为空池出口建立服务，配置中不得出现指向不存在 tag 的 route rule；页面和 API 应返回明确提示。

### KI-002（P1）服务 Stop 的目标 `direct` 不在 selector 成员中

- 位置：`app/singbox/config.py::_build_selectors`、`app/services.py::stop_service`
- 现状：selector 的 `outbounds` 仅包含 `n{id}` 节点；Stop 却调用 Clash API 将 selector 切换到 `direct`。
- 影响：单个服务的 Stop 操作可能被 Clash API 拒绝，页面无法把服务切到直连状态。
- 建议：将 `direct` 加入每个需要支持 Stop 的 selector，并明确默认节点仍为池中第一项；如 Stop 应表示“阻断”，则改用 `block` 并同样加入成员。
- 验收：运行中的服务可在节点、`direct`（或最终确定的 `block`）之间往返切换，`GET /proxies/{group}` 的 `now` 与页面状态一致。

### KI-003（P1）当前运行时数据没有节点和出口池成员

- 类型：部署数据状态，不是代码缺陷。
- 2026-08-24 检查结果：2 个订阅、0 个节点、7 个入口、7 个非 direct 出口、0 个池成员、6 个服务，其中 5 个标记 auto-start。
- 影响：当前数据库无法形成可工作的代理出口；部分服务指向空池出口。
- 建议：修复 KI-001/004 后重新刷新订阅，检查解析结果，再重新建立出口池关联。操作前保留数据库备份。
- 验收：至少一个订阅刷新得到节点；每个非 direct 服务的出口池至少有一个有效节点；生成配置通过 `sing-box check` 和真实流量测试。

### KI-004（P1）订阅解析为 0 时直接清空旧节点

- 位置：`app/services.py::refresh_subscription`
- 现状：只要 HTTP 请求没有抛异常，即使返回登录页、限流页或暂不支持的格式导致解析结果为 0，也会清空该订阅已有节点。
- 影响：一次异常订阅响应会删除节点，并通过外键级联清除出口池关联。
- 建议：默认保留旧节点并返回失败；只有明确识别为合法空订阅或用户确认时才清空。可增加响应类型识别、最小节点数保护和事务化快照。
- 验收：已有节点的订阅收到 HTML、空正文或无法解析内容时，旧节点和出口池关联保持不变。

### KI-005（P2）`auto_start` 只保存，不执行

- 位置：`app/db/service.py::get_auto_start_services`、应用启动流程
- 现状：页面和数据库支持 `auto_start`，但没有启动钩子读取并执行。
- 影响：界面显示的 “auto-start on boot” 与实际行为不一致。
- 建议：先明确它表示“应用启动时启动整个 sing-box”还是“sing-box 就绪后将指定 selector 切到默认节点”，再实现单一启动协调器；在此之前可暂时隐藏该选项。
- 验收：重启应用后，仅标记的服务进入约定状态；启动失败有日志且不会阻塞 Web 应用。

### KI-006（P2）sing-box 启动只检查短暂存活，不等待控制面就绪

- 位置：`app/singbox/process.py::start`
- 现状：启动后等待 0.2 秒并检查进程是否退出，没有等待 Clash API 可访问，也没有在启动前执行 `sing-box check`。
- 影响：API 可能报告启动成功，但进程随后退出，或 Clash API 尚未就绪导致紧接着的状态查询/切换失败。
- 建议：写入临时配置后先执行 `sing-box check`；启动后在限定时间内轮询 Clash API/进程状态，失败时返回 stderr 摘要并清理进程。
- 验收：无效配置、端口占用和控制端口未就绪都必须返回失败；成功响应后 Clash API 可立即使用。

### KI-007（P2）Web 端口和 `PROXYHUB_HOME` 文档与实现不一致

- 位置：`run.py`、`app/settings.py`、`docs/settings.md`
- 现状：`web_port` 可在设置页保存，但 `run.py` 固定监听 8080；文档声明支持 `PROXYHUB_HOME`，实现的 `BASE_DIR` 没有读取该环境变量。
- 影响：用户修改设置后没有效果；部署路径行为与文档不一致。
- 建议：启动时读取已验证的 `web_port`；恢复环境变量覆盖或修正文档，并避免在模块 import 阶段固定所有路径。
- 验收：修改端口并重启后监听端口改变；设置 `PROXYHUB_HOME` 后所有运行时文件落到指定目录。

### KI-008（P2）API 缺少统一参数校验和错误响应

- 位置：`app/routes.py`、`templates/base.html::api`
- 现状：多数接口直接索引 JSON 字段并让数据库异常冒泡；前端 fetch 封装不检查 `response.ok`，每个调用点自行判断 `success`。
- 影响：缺字段、无效协议、端口冲突、外键限制等情况可能返回 HTML 500 或让页面误判结果，排错体验不稳定。
- 建议：增加轻量请求校验与统一 JSON error handler；前端封装在非 2xx 时统一抛出包含后端 message 的异常。
- 验收：典型无效输入均返回结构一致的 4xx JSON，页面显示准确错误且不会刷新成“保存成功”。

### KI-013（P1）节点测速无条件重启正在运行的 sing-box

- 位置：`app/web/api/nodes.py::_ensure_singbox_with_nodes`、`app/services/runtime.py::apply_config`、`app/singbox/process.py::restart`
- 现状：每次单节点或批量测速前，如果 sing-box 已运行，都会重新生成并写入配置，然后执行 `stop + start`；当前没有判断生成后的配置内容是否发生变化。
- 影响：重复测速也会中断正在工作的代理连接；连续或并发测速可能造成频繁重启，影响所有绑定服务，而不仅是被测节点。
- 原因：URL 测速通过 Clash API 访问 `n{id}`，需要保证节点已加载进 sing-box；当前用无条件重启保证配置新鲜，但粒度过大。
- 建议：对规范化后的配置内容计算稳定 hash，并记录当前进程成功加载的配置 hash。测速前只生成和比较：未运行时写入并启动；运行中且 hash 相同则直接测速；hash 不同时先校验、原子写入并只重启一次。配置比较和重启流程需要加锁，避免并发测速重复重启。
- 验收：配置未变化时连续执行单节点、分组和全部测速，sing-box PID 必须保持不变；节点或路由配置变化后首次测速只重启一次并加载新配置；并发测速不会触发多次重启。

## 4. 测试与工程问题

### KI-009（P1）配置单元测试会写入并删除真实运行路径

- 位置：`test/test_config.py::TestWriteConfig`
- 现状：测试直接调用 `write_config()`，使用实际 `data/config.json`，结束时删除该文件。
- 影响：在已有部署目录运行测试可能覆盖或删除正在使用的配置。
- 建议：通过临时目录和依赖注入/monkeypatch 隔离 `CONFIG_PATH`，测试不得接触真实 `data/`。
- 验收：测试前后 `data/` 内容和 mtime 完全不变。

### KI-010（P2）测试套件混合了单元测试、手工冒烟和破坏性升级脚本

- 位置：`test/test_process.py`、`test/test_upgrade.py`
- 现状：两个 `test_*.py` 是带 `main()` 的独立脚本，不会被 unittest 自动发现；process 测试依赖真实网络和端口，upgrade 测试可能下载并替换二进制。
- 影响：“112 tests passed”不包含进程和升级真实链路，测试命名容易造成覆盖率误解。
- 建议：拆为 `tests/unit/`、`tests/integration/` 和 `scripts/manual/`；破坏性测试需显式开关和临时资源。
- 验收：默认测试无网络、无真实运行时写入；集成测试单独执行并清楚报告跳过原因。

### KI-011（P2）数据库、路由、服务层和 Clash API 缺少自动化覆盖

- 现状：现有测试主要覆盖 parser、protocol、config、settings 和 logger。
- 影响：CRUD、外键级联、订阅刷新保护、认证、API 状态码和 selector 切换回归无法被及时发现。
- 建议：优先补 KI-001/002/004 的回归测试，再补隔离 SQLite 的 API 测试和 Clash API mock 测试。

### KI-012（P3）依赖和持续集成基线不足

- 现状：`requirements.txt` 只有未固定版本的 `flask`、`pyyaml`，没有声明测试工具、Python 版本范围、格式化/静态检查或 CI。
- 影响：重新构建的依赖不可复现，兼容性问题只能在部署时暴露。
- 建议：固定直接依赖的兼容范围或锁文件；增加最小 CI（编译、单元测试、配置样例 check）。

## 5. 本轮验证记录

| 检查 | 结果 |
|---|---|
| `python3 -m compileall -q app run.py` | 通过 |
| `python3 -m unittest discover -s test -v` | 112 项通过 |
| 隔离 API CRUD 冒烟 | 订阅、模拟刷新、节点、入口、出口池、服务创建通过 |
| sing-box 版本 | 1.13.19 linux/amd64 |
| 完整样例 `sing-box check` | 通过 |
| 本沙箱真实启动 | 未完成；运行时因沙箱权限报 `subscribe route updates: operation not permitted`，需在真实部署主机复测 |

## 6. 建议修复顺序

1. KI-001、KI-002、KI-004、KI-009、KI-013：先保证路由语义、数据安全和测速不影响现有流量。
2. 在真实 Docker/主机环境完成启动、停止、重启、代理流量和 selector 切换验收。
3. KI-006、KI-008、KI-011：补启动就绪检查、统一错误处理和关键回归测试。
4. KI-005、KI-007：补齐界面承诺的功能和设置语义。
5. 其余工程优化按 [architecture-improvements.md](architecture-improvements.md) 分阶段执行。
