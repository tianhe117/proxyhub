# ProxyHub 个人版第一版需求评审待修改项

本文记录评审过程中已确认、但计划后续统一写入 `docs/01-requirements.md` 的修改项。本文不是正式需求依据。

## 待修改

### `1.2 第一版原则` 补充基本防护与防止过度设计

- ProxyHub 第一版是纯个人使用的软件，默认运行在由单一可信用户管理的环境中，主要保证通过正常页面和内部 API 执行的正常操作路径正确、稳定、可排错。
- 第一版只实现保障核心数据和运行流程所必需的基本防护，包括必要的输入校验、业务不变量校验、关键文件原子替换、生命周期串行化和错误日志；已有明确需求规定的事务、失败保护和一致性约束仍须实现。
- 不为恶意调用、绕过页面直接构造异常请求、人工直接修改数据库或程序生成的正式配置、在不支持的环境中运行或其他非正常操作设计额外兼容和恢复机制。
- 不为发生概率很低、且不会破坏核心数据或造成持续性错误的边缘情况增加复杂状态、重试、回滚、冗余备份、兼容分支或抽象层。遇到此类情况时，采用简单失败、记录错误或重新启动等符合现有需求的处理方式。
- 设计和实现阶段不得以“以后可能需要”作为增加复杂度的充分理由；只有当前第一版的明确需求或实际正常使用路径需要时，才增加相应机制。
- 上述原则不覆盖或削弱其他已经明确写入需求的行为；如果某项具体需求规定了校验、事务、回滚或恢复规则，以具体需求为准。
- 建议在现有 `REQ-GEN-005` 后增加一条需求：第一版面向单一可信用户和正常操作路径，只实现保护核心数据与运行流程所需的基本防护；不为恶意、非正常或低概率操作增加复杂兼容、恢复或高可靠机制。除非具体需求另有明确规定，设计和实现应选择满足当前需求的最简单方案。

### Subscription 运行状态限制

- 统一在 `7.1 运行期间允许的修改` 中描述，不在 `5. 订阅管理` 重复规定。
- 补全 `REQ-CONFIG-001`：sing-box running 时，除禁止刷新 Subscription 外，还应明确禁止新增、修改和删除 Subscription。
- 建议后续将 `REQ-CONFIG-001` 统一表述为：sing-box running 时，禁止新增、修改、删除或刷新 Subscription，禁止新增、修改或删除 Node、Inbound 和 Route，禁止新增或删除 Outbound，以及修改 Outbound 名称、mode、Node Pool、Fallback/Candidate 角色等会改变配置结构的内容。`REQ-CONFIG-002` 明确允许的 Manual/Auto Node priority 调整不属于此处禁止的 Outbound 结构修改。
- 修改 `REQ-UI-002`，将桌面页面的 Subscription 管理能力由“刷新订阅”补全为“新增、修改、删除和刷新订阅”。建议完整表述为：桌面页面支持新增、修改、删除和刷新 Subscription、人工检测 Node、切换 Manual 当前节点、Start、Stop、Restart、下载日志以及人工检查和升级 sing-box。
- `REQ-UI-002` 只定义桌面页面提供的操作入口；Subscription 新增、修改、删除和刷新的运行状态限制统一遵循 `REQ-CONFIG-001`，删除和刷新产生的差异预览、级联影响与事务规则仍遵循 Subscription 管理章节。
- 后续修改时检查 `3.5 订阅刷新`、`3.6 人工修改配置` 与 `REQ-CONFIG-001` 的表述一致性。

### 统一 TCP 与 URL 检测流程

- 删除“Hysteria2 基于 QUIC/UDP，不执行 TCP 检测”的描述，不按 Node 协议设置检测流程特判。
- 所有受支持协议的 Node（包括 Hysteria2）统一先检测该 Node 配置的服务器地址和端口是否可通过 TCP 连接，再继续执行 URL 检测。TCP 检测失败也不得跳过或阻止 URL 检测。
- Node 的最终健康结果只由 URL 检测结果决定。TCP 检测结果和 `tcp delay` 只供页面查看与人工排错，不参与 available/unavailable 判定、Auto Outbound 连续失败计数、自动切换或其他控制判断。
- 后续修改 `REQ-HEALTH-001` 和 `REQ-HEALTH-002` 时删除 Hysteria2 例外和“TCP 失败立即结束”的规则，并同步删除 `docs/00-project-plan.md` 中的“Hysteria2 特殊处理”；历史讨论记录不回改。

### Node TCP 与 URL Delay 状态

- 修改 `REQ-HEALTH-005`，Node 不保存检测中的中间状态，也不区分 `last result`、`cur result` 或 `checking`。Node 运行时健康状态保持为以下简单字段：

```text
result: unknown / available / unavailable
tcp delay
url delay
last checked time
failure reason
```

- `result` 始终表示最近一次已经完成的检测结果。尚无任何已完成检测时为 `unknown`。
- `tcp delay` 和 `url delay` 均以毫秒记录。最近一次检测中 TCP 或 URL 未取得有效 delay 时，对应字段为空，不得继续保留更早批次的旧值。
- TCP 检测无论成功或失败都继续 URL 检测。最终 `result` 只由 URL 检测决定：URL 检测成功时为 `available`，失败时为 `unavailable`；TCP 检测结果不改变 `result`。
- `failure reason` 只记录最近一次已完成检测中决定最终健康结果的 URL 检测失败原因；URL 检测成功时为空。TCP 检测未取得有效 delay 时只将 `tcp delay` 置空，不增加单独的 TCP 结果或失败原因字段。
- 一次检测过程中产生的 TCP delay、URL delay、result 和 failure reason 均作为该检测批次的临时数据，不立即修改 Node 已保存的运行时健康状态。检测全部完成后，一次性更新 `result`、`tcp delay`、`url delay`、`last checked time` 和 `failure reason`。
- 检测执行期间，Node 继续保持最近一次已完成检测的完整状态，不向 Node 运行时状态增加 `checking` 字段。检测任务是否正在执行由检测调度逻辑自身管理。
- 同步修改 `REQ-HEALTH-008` 以及页面、日志中的 delay 表述，明确展示或记录 TCP delay 与 URL delay，不再使用未注明类型的单一 delay。

### 认证需求精简

- 修改 `REQ-AUTH-001`，保留默认用户名为 `admin`、默认密码为空以及密码为空时跳过认证的行为，删除“页面持续显示醒目安全警告”的要求。
- `REQ-AUTH-001` 建议改为：登录使用用户名和密码。默认用户名为 `admin`，默认密码为空；密码为空时按个人部署需求跳过认证。
- 删除整个 `REQ-AUTH-004`，第一版需求不规定 CSRF 防护、Cookie 的 HttpOnly/SameSite/Secure 属性，也不需要关于角色权限、企业级风控或复杂防暴力破解的范围声明。
- 删除整个 `REQ-AUTH-005`，第一版需求不规定 ProxyHub 公网 TLS 终止方式，也不要求部署文档说明 Nginx、监听地址或防火墙的安全边界。
- 保留现有 `REQ-AUTH-002` 和 `REQ-AUTH-003`；删除 `REQ-AUTH-004`、`REQ-AUTH-005` 后无需调整剩余 AUTH 编号。

### Settings JSON 错误回退

- `data/settings.json` 无法读取或不是合法 JSON、因而无法取得设置内容时，不应用该文件、不覆盖原文件，也不使用默认值替代损坏文件继续启动 sing-box；保留原文件并报告错误，等待用户修正。
- 文件能够读取并解析为合法 JSON 对象时，允许缺少部分已定义字段；缺失字段使用对应的内置默认值补全后，再对完整设置执行校验。
- 文件中已提供但值非法的字段不得使用默认值静默替代；未知结构或补全后的完整设置校验失败时，按无法应用设置处理，保留原文件并报告错误。
- 内置默认值补全只发生在内存加载过程中，不因启动加载而自动重写 `data/settings.json`。用户后续通过 Settings 页面成功保存时，再按 `REQ-SETTINGS-003` 写入经过完整校验的设置。
- `REQ-SETTINGS-006` 建议改为：`data/settings.json` 无法读取、不是合法 JSON、包含未知结构或补全后仍无法通过校验时，ProxyHub 不应用该文件，保留原文件并明确报告错误，且不得启动 sing-box；文件能够解析为合法 JSON 对象但缺少部分已定义字段时，使用对应内置默认值补全，并在完整校验通过后加载。

### sing-box 64 位架构范围

- 第一版只支持 `amd64` 架构，所有正式需求、页面和日志统一使用 `amd64`，不再并列使用 `x86_64`。
- `REQ-UPGRADE-001` 建议改为：ProxyHub Web 在 sing-box 不存在时仍可运行，状态显示“未安装”并保持 stopped。用户可以人工下载官方 GitHub Release 中适用于 `amd64` 的 sing-box。
- 下载与升级流程只匹配和安装 `amd64` 资产，不支持 32 位 x86、arm64 或其他架构。
- `REQ-DEPLOY-002` 建议改为：支持 Ubuntu 20.04 及以上版本、`amd64` CPU；不要求支持 Windows、macOS、其他 Linux 发行版或 arm64。
- 同步修改下载资产匹配、架构校验、页面和日志中的架构名称，统一使用 `amd64`。

### sing-box 版本展示与升级条件

- sing-box 二进制存在时，无论当前为 running 还是 stopped，页面都显示检测到的本地当前版本；二进制不存在时显示“未安装”。
- sing-box 为 stopped 或二进制不存在时，允许检查远程新版本，并根据当前安装状态执行下载、安装或升级。
- sing-box 为 running 时，不允许检查远程新版本、下载或升级，只显示本地当前版本。
- 下载、安装或升级成功后保持 stopped，不自动启动 sing-box。
- `REQ-UPGRADE-002` 建议改为：sing-box 二进制存在时，页面始终显示本地当前版本。sing-box stopped 或二进制不存在时，允许检查新版本并下载、安装或升级；running 时禁止检查新版本、下载和升级。成功下载、安装或升级后不自动启动 sing-box。
- 修改 `REQ-UPGRADE-003` 第 4 步为“任一步失败都保留原二进制、记录错误日志，并在发起操作的页面显示简单失败提示”。第一版不要求专项错误页面或复杂失败报告。

### Manual/Auto Outbound 统一 Node priority

- Manual Outbound 和 Auto Outbound 使用相同的 Node Pool priority 规则。每个 Node 在所属 Outbound 中都有连续、唯一的 1 至 N priority，数值越小、优先级越高，并在页面中排列得越靠前。
- 新建 Outbound 时，前端必须提交确定的 Node 顺序：逐个选择 Node 时按选择先后排序；一次同时选择多个 Node 时按 Node name 排序。后端按前端提交顺序生成 priority，不再另外推断选择顺序。
- Outbound 是至少包含两个 Node 的代理节点池，并以 `manual` 或 `auto` mode 属性决定运行策略。第一版不支持只有一个 Node 的 Outbound，新建 Outbound 的默认 mode 为 `manual`。
- Manual Outbound 的 priority 只用于页面展示和配置中的 Node 顺序，不参与健康判断、自动故障切换或自动选择。
- 新建 `auto` Outbound 时必须明确指定一个 Fallback Node；页面可以默认选中 priority 最高的 Node，但保存前必须清楚显示该选择。Fallback Node 也保留自身 priority，用于页面展示和配置中的 Node 顺序，但不参与 Candidate 自动择优；除 Fallback Node 外的其他 Node 都是 Candidate，并按 priority 执行原有自动选择和优先级恢复。
- 修改 mode 只改变 Outbound 的运行策略，不改变 Node Pool、priority 或已指定的 Node：`manual` 改为 `auto` 时，原持久化 Current Node 直接成为 Fallback Node；`auto` 改为 `manual` 时，原 Fallback Node 直接成为持久化 Current Node。不再定义独立的类型转换流程。
- 业务需求不引入统一的“default Node”概念。Manual Outbound 使用“持久化 Current Node”，Auto Outbound 使用“Fallback Node”；sing-box selector 的 `default` 只作为 `7.2 配置生成` 中的配置字段映射。

### 系统内置 Direct Outbound

- Outbound 在业务上分为用户创建的 Proxy Outbound 和系统内置的 Direct Outbound。Proxy Outbound 保存于数据库并使用 `manual` 或 `auto` mode；Direct Outbound 全局唯一、只读，不保存为数据库中的 Outbound 记录。
- 前端和内部 API 始终正常提供 Direct Outbound，并使用稳定的系统标识将其显示为只读固定项。Direct 可以作为 Route 目标，但不能新增、修改或删除。
- 每条 Route 都必须明确选择目标类型，目标只能是 Direct Outbound 或一个现存的 Proxy Outbound。不得使用目标缺失、空引用或无效 Outbound 引用隐式表示 Direct。
- 必须区分“没有 Route”和“Route 选择 Direct”：Inbound 没有 Route 时不写入 sing-box 配置，也不监听；Inbound 的 Route 明确选择 Direct Outbound 时正常监听并直连。
- sing-box 配置生成时为 Direct Outbound 创建固定且保留的 direct tag。该配置对象不属于用户持久化业务数据。

### `6. Inbound、Outbound 与 Route` 整章重写

- 将本章按“Inbound、Proxy Outbound、Manual/Auto mode、Route 与系统内置 Direct、级联删除”重新组织，不再设置 Manual/Auto 转换小节。
- 本章定义业务对象、Node Pool、priority、mode、Current Node、Fallback Node、Route 的明确目标和切换时必须达到的业务效果；`outbounds`、`default`、`interrupt_exist_connections` 及 Direct 的 sing-box 配置映射统一由 `7.2 配置生成` 规定。
- 第 2 章只保留模型总览和真正需要作为全局不变量的内容。与 Outbound、Route 具体行为重复的规范性要求应尽量由第 6 章唯一规定，避免保留两套语义相同的 REQ。
- 建议使用以下内容整体替换当前第 6 章。

#### 6.1 Inbound

**REQ-INBOUND-001** 系统允许创建任意数量的 Inbound，支持 HTTP、SOCKS、Mixed、Shadowsocks 和 VMess。

**REQ-INBOUND-002** 每个 Inbound 独立定义名称、监听协议、监听地址、监听端口和该协议所需的认证参数。Mixed 在同一端口兼容 HTTP 和 SOCKS。

**REQ-INBOUND-003** 未绑定 Route 的 Inbound 只保存于数据库，不写入 sing-box 配置，也不对外监听。

#### 6.2 Outbound 通用约束

**REQ-OUTBOUND-001** 用户创建的 Proxy Outbound 是由 Node 组成的代理节点池，并通过 `manual` 或 `auto` mode 属性决定运行策略。系统内置 Direct Outbound 不使用 Node，其规则由 `6.4 Route、Direct 与级联删除` 规定。

**REQ-OUTBOUND-002** 每个 Proxy Outbound 必须始终至少包含两个不同 Node。Node 是全局对象，可以被多个 Proxy Outbound 复用，但在同一个 Node Pool 中只能出现一次。用户正常创建或编辑 Node Pool 时，少于两个 Node 不允许保存；全局 Node 删除、Subscription 删除或订阅刷新造成不足两个 Node 时，按 `REQ-ROUTE-007` 和 `REQ-ROUTE-008` 执行预览及级联删除。

**REQ-OUTBOUND-003** Outbound Node Pool 中的每个 Node 都必须具有连续、唯一的 1 至 N priority，数值越小、优先级越高。页面按 priority 从高到低显示 Node；priority 的运行用途由 mode 决定。

**REQ-OUTBOUND-004** 新建 Outbound 时，前端必须提交确定的 Node 顺序：逐个选择 Node 时按选择先后排序，一次同时选择多个 Node 时按 Node name 排序。后端按前端提交顺序生成 priority。后续调整顺序时，保存后重新整理为连续、唯一的 1 至 N priority；修改 priority 不改变 Manual Outbound 的 Current Node 或 Auto Outbound 的 Fallback Node。

**REQ-OUTBOUND-005** Proxy Outbound 的 Current Node 和 Fallback Node 必须属于其 Node Pool。正常编辑 Node Pool 时，如果移除 `manual` Current Node 或 `auto` Fallback Node，但仍保留至少两个 Node，则以保存后 priority 最高的 Node 自动替代。Current Node 发生运行时切换时，必须中断仍绑定旧节点的已有入站连接，使后续重连使用新的 Current Node；实现该业务效果的具体 sing-box 配置字段由 `7.2 配置生成` 统一规定。

#### 6.3 Manual/Auto mode

**REQ-OUTBOUND-006** Outbound 的 mode 只能是 `manual` 或 `auto`，新建时默认为 `manual`。只有 sing-box stopped 时才能修改 mode；修改 mode 只改变运行策略，不增加、删除或重新排序 Node。

**REQ-OUTBOUND-007** `manual` mode 不执行自动故障切换。priority 只用于页面展示和配置中的 Node 顺序；新建 Outbound 时 priority 最高的 Node 成为初始持久化 Current Node。用户可以在 sing-box running 时人工切换 Current Node，只有 Clash API 明确确认成功后才持久化新选择；切换失败时保留原选择并在页面提示失败。人工切换不改变 priority。

**REQ-OUTBOUND-008** 新建 `auto` Outbound 时必须从 Node Pool 中明确指定一个 Fallback Node，页面可以默认选中 priority 最高的 Node，但保存前必须清楚显示该选择；已有 Outbound 从 `manual` 改为 `auto` 时，原持久化 Current Node 直接成为 Fallback Node，不再要求重新选择。除 Fallback Node 外的其他 Node 全部是 Candidate Node。Fallback Node 的 priority 只用于页面展示和配置顺序，不参与 Candidate 自动择优；Candidate 按 priority 执行自动选择和 Candidate Priority Recovery。

**REQ-OUTBOUND-009** `auto` mode 的运行时 Current Node 完全由后台控制循环管理，不持久化，用户不能临时人工切换或锁定。每次实际启动或重启后，Current Node 从 Fallback Node 初始化。未被 Route 引用的 `auto` Outbound 不运行自动检测、故障切换、Fallback Recovery、Candidate Priority Recovery 或 Fallback 超时重启控制。

**REQ-OUTBOUND-010** 将 mode 从 `manual` 改为 `auto` 时，原持久化 Current Node 直接作为 Fallback Node；将 mode 从 `auto` 改为 `manual` 时，原 Fallback Node 直接作为持久化 Current Node，修改前的 Auto 运行时 Current Node 不保留。修改 mode 时保留原 Node Pool 和全部 priority，不要求用户重新选择 Node 或排序，并清除该 Outbound 的临时控制状态。

#### 6.4 Route、Direct 与级联删除

**REQ-ROUTE-001** Route 只表达一个 Inbound 的流量目标，不提供规则分流或额外“服务”业务层。每条 Route 必须引用一个 Inbound，并明确选择系统内置 Direct Outbound 或一个现存的 Proxy Outbound 作为目标；不得以目标缺失、空引用或无效引用表示 Direct。

**REQ-ROUTE-002** 一个 Inbound 最多被一条 Route 引用；一个 Proxy Outbound 可以被零条、一条或多条 Route 引用。多条 Route 引用同一个 Proxy Outbound 时，共享其 Node Pool、Current Node 和运行状态。任意数量的 Route 可以选择系统内置 Direct Outbound。

**REQ-ROUTE-003** Direct Outbound 是系统内置、全局唯一的只读 Outbound。前端和内部 API 始终使用稳定的系统标识提供该对象，并允许将其选为 Route 目标，但不允许新增、修改或删除；数据库不保存对应 Outbound 记录。Direct Outbound 不包含 Node，不存在 mode、priority、Current Node 或健康状态，也不执行节点检测和自动故障切换。

**REQ-ROUTE-004** Inbound 没有 Route 时只保存于数据库，不写入 sing-box 配置，也不对外监听；Inbound 的 Route 选择 Direct Outbound 时正常写入配置并对外监听，流量直接访问目标地址。

**REQ-ROUTE-005** 配置生成时，系统为 Direct Outbound 生成固定且保留的 sing-box direct tag，并将所有选择 Direct 的 Route 映射到该 tag。该配置对象不属于用户持久化业务数据。

**REQ-ROUTE-006** 删除 Inbound 或 Proxy Outbound 时，一并删除引用它的 Route。删除 Proxy Outbound 不得把原 Route 自动或静默改为 Direct；Direct Outbound 不可删除。

**REQ-ROUTE-007** 删除 Node 后，从所有 Proxy Outbound Node Pool 中删除该 Node 的引用，并按以下规则继续处理：

- Outbound 剩余至少两个 Node：保留 Outbound 和其余 Node 的相对顺序，重新整理为连续、唯一的 1 至 N priority；
- `manual` Outbound 的持久化 Current Node 被删除时，以剩余 Node 中 priority 最高者作为新的持久化 Current Node；
- `auto` Outbound 的 Fallback Node 被删除时，以剩余 Node 中 priority 最高者作为新的 Fallback Node；
- Outbound 剩余不足两个 Node：删除该 Outbound，并继续删除引用它的全部 Route。

**REQ-ROUTE-008** 人工删除 Node、删除 Subscription 和订阅刷新删除 Node 都使用相同的级联规则，并在执行前向用户展示完整影响，包括 Current/Fallback Node 的自动替换、Proxy Outbound 删除和 Route 删除；用户确认后在同一个业务事务中完成 Node、Outbound 和 Route 的变更。

#### 后续同步检查

- 正式合并时将 `docs/01-requirements.md` 文档版本升级为 `v0.2`，更新日期并继续保持“待评审”；本文仍作为待修改记录，不提升为正式需求依据。
- 同步更新 `2.1 核心关系`、`2.2 名词` 和 `2.3 全局不变量`：Proxy Outbound 是至少包含两个 Node、以 mode 区分运行策略的用户业务对象；Direct Outbound 是前端和内部 API 可见、全局唯一、只读且不保存数据库记录的系统对象；Route 必须引用 Inbound 并明确选择 Direct 或一个现存 Proxy Outbound。第 2 章只保留模型总览和真正的全局约束，具体行为由第 6 章统一定义。
- 同步更新 `3.1 首次安装与配置`、`3.6 人工修改配置` 和 `8.1 期望状态`：系统内置 Direct 可以作为有效 Route 目标；没有 Route 与选择 Direct 的 Route 含义不同；只包含 Direct Route 的配置也属于可以启动的有效配置。
- 同步更新 `5.4 差异确认与事务`：预览除显示被删除的 Proxy Outbound 和 Route 外，还必须显示因 Node 删除导致的持久化 Current Node 或 Fallback Node 自动替换；Subscription 删除和刷新继续使用同一事务边界。
- 同步更新 `7.1 运行期间允许的修改`：补全 Subscription 新增、修改、删除和刷新均只能在 sing-box stopped 时执行；Outbound mode 只能在 stopped 时修改；Manual 和 Auto Outbound 的 priority 调整在 running 时均允许保存，且不因保存操作立即切换 Current Node。Auto 的新 priority 在后续自动选择时生效，Manual 的新 priority 只影响页面顺序及下次生成的完整配置。
- 同步更新 `7.2 配置生成`，并由该节唯一规定配置映射：所有已保存的 Proxy Outbound 均按 mode 写为 selector，包括未被 Route 引用者；selector 的 `outbounds` 按 Node Pool priority 包含全部 Node；`manual` selector 的 `default` 映射为持久化 Current Node，`auto` selector 的 `default` 映射为 Fallback Node；两种 mode 均设置 `interrupt_exist_connections: true`。系统内置 Direct Outbound 映射为固定且保留的 sing-box direct tag，不持久化为 Outbound 数据；选择 Direct 的 Route 映射到该 tag。第 `7.2` 不再创建“default Node”业务概念。
- 同步检查 `8.2 启停与重启`：Manual 恢复持久化 Current Node，Auto 从 Fallback 初始化。
- 同步检查第 10 章：`Auto Outbound` 统一表示 `mode = auto` 的 Proxy Outbound；Fallback Node 虽具有 Node Pool priority，但始终排除在 Candidate 检测、自动择优和 Priority Recovery 之外；Candidate 比较直接使用各自在完整 Node Pool 中的 priority，不要求 Candidate 自身重新编号为 1 至 N。
- 同步检查后续故障切换章节中关于 selector 切换后中断已有连接的要求，避免与 `REQ-OUTBOUND-005` 重复定义；后续章节只描述运行时何时切换。
- 同步更新第 11 章页面与内部 API：Outbound 页面和 Route 目标均提供只读 Direct 系统项；Proxy Outbound 只使用 mode 属性，不提供类型转换向导；Manual/Auto priority 都可调整；Direct 不显示 Node、Current Node 或健康状态。
- 同步更新第 14 节可靠性要求和第 16 节冻结检查清单：删除 Proxy Outbound 不能把 Route 静默改为 Direct；验收需要覆盖无 Route、Direct Route、Proxy Route、mode 修改、最少两个 Node、priority 以及级联删除。
- 同步更新 `docs/00-project-plan.md` 的数据模型、sing-box 映射、页面/API、测试分类和发布前验收：Direct 改为非持久化系统 Outbound，Route 目标必须显式；Manual/Auto 改为 mode；全部 Proxy Outbound 至少两个 Node 并共享 priority 规则；删除 Fallback Node 的验收结果改为按 priority 自动替换或在节点不足时级联删除。
- 如果启用 sing-box cache file，必须避免缓存的 selector 历史选择覆盖 Manual 持久化 Current Node 或 Auto Fallback 初始化规则；具体方案留待 sing-box 集成设计确定。
- 历史讨论文档继续只用于追溯，不回改其中已经被 v0.2 替代的 Direct、节点数量或类型转换口径。

### v0.2 合并核对结论

- 当前待修改项之间没有发现仍需产品决策的直接冲突，可以作为 `docs/01-requirements.md` v0.2 的合并输入。
- v0.2 必须一次性更新正式需求中的文档元数据、第 1/2/3/5/6/7/8/9/10/11/13/14/16 节及 `docs/00-project-plan.md`；不能只替换第 6 章，否则会保留 Direct、Route 基数、单 Node Manual、Candidate 独立编号、Hysteria2 检测和 Settings 错误处理等旧口径。
- 历史讨论文件不参与一致性判断，也不需要随 v0.2 修改。
- `Direct` 的稳定系统标识、Route 目标的物理存储字段、selector tag 命名和 cache file 处理仍属于后续数据模型、API 和 sing-box 集成设计，不阻止需求升级；设计不得改变“Direct 显式可选、前后端可见、只读且无数据库 Outbound 记录”的产品语义。
