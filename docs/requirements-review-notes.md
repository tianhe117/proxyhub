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
- 建议后续将 `REQ-CONFIG-001` 统一表述为：sing-box running 时，禁止新增、修改、删除或刷新 Subscription，禁止新增、修改或删除 Node、Inbound 和 Route，禁止新增或删除 Outbound，以及修改 Outbound 名称、类型、Node Pool、Fallback/Candidate 角色等会改变配置结构的内容。`REQ-CONFIG-002` 明确允许的 Auto Candidate 排序不属于此处禁止的 Outbound 结构修改。
- 修改 `REQ-UI-002`，将桌面页面的 Subscription 管理能力由“刷新订阅”补全为“新增、修改、删除和刷新订阅”。建议完整表述为：桌面页面支持新增、修改、删除和刷新 Subscription、人工检测 Node、切换 Manual 当前节点、Start、Stop、Restart、下载日志以及人工检查和升级 sing-box。
- `REQ-UI-002` 只定义桌面页面提供的操作入口；Subscription 新增、修改、删除和刷新的运行状态限制统一遵循 `REQ-CONFIG-001`，删除和刷新产生的差异预览、级联影响与事务规则仍遵循 Subscription 管理章节。
- 后续修改时检查 `3.5 订阅刷新`、`3.6 人工修改配置` 与 `REQ-CONFIG-001` 的表述一致性。

### 统一 TCP 与 URL 检测流程

- 删除“Hysteria2 基于 QUIC/UDP，不执行 TCP 检测”的描述，不按 Node 协议设置检测流程特判。
- 所有受支持协议的 Node（包括 Hysteria2）统一先检测该 Node 配置的服务器地址和端口是否可通过 TCP 连接，再继续执行 URL 检测。TCP 检测失败也不得跳过或阻止 URL 检测。
- Node 的最终健康结果只由 URL 检测结果决定。TCP 检测结果和 `tcp delay` 只供页面查看与人工排错，不参与 available/unavailable 判定、Auto Outbound 连续失败计数、自动切换或其他控制判断。
- 后续修改 `REQ-HEALTH-001` 和 `REQ-HEALTH-002` 时删除 Hysteria2 例外和“TCP 失败立即结束”的规则，并同步删除 `docs/00-project-plan.md` 中的“Hysteria2 特殊处理”；历史讨论记录不回改。

### Node TCP 与 URL Delay 状态

- 修改 `REQ-HEALTH-005`，不为 TCP 检测建立单独的复杂结果状态。Node 运行时状态保持为以下简单字段：

```text
last result: unknown / available / unavailable
cur result: available / unavailable
checking: true / false
tcp delay
url delay
last checked time
failure reason
```

- `cur result` 表示当前检测批次由 URL 检测得出的实际结果；`last result` 保留上一个已完成批次的结果。尚无已完成批次时，`last result` 为 `unknown`。
- `tcp delay` 和 `url delay` 均以毫秒记录。TCP 或 URL 检测未取得有效 delay 时，对应字段为空，不得继续展示上一个批次的旧值。
- TCP 检测无论成功或失败都继续 URL 检测。URL 检测成功时 `cur result` 为 `available`，失败时为 `unavailable`；TCP 检测结果不改变 `cur result`。
- `checking` 期间继续展示 `last result`；当前批次结束后，一次性更新 `cur result`、`tcp delay`、`url delay`、last checked time 和 failure reason，避免页面观察到不同批次拼接的状态。当前批次完成后，其 `cur result` 作为下一批次开始时的 `last result`。
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

### Manual Outbound 稳定 Node 顺序（替代优先级与排序）

- Manual Outbound 的 Node 不定义优先级，第一版不提供人工排序；只保存当前 Manual Outbound 自身的稳定 Node 顺序，不使用 Node 的全局创建时间或其他全局顺序。
- 新建 Manual Outbound 时，直接采用前端提交的 Node 顺序形成初始稳定 Node 顺序，不额外规定前端如何组织该顺序；后续新加入的 Node 追加到末尾。
- 稳定 Node 顺序用于确定配置中的节点顺序和 Current Node 被删除后的回退节点，不参与健康判断、自动故障切换或自动选择。
- 新建 Manual Outbound 时至少选择一个 Node，稳定 Node 顺序中的第一个 Node 成为初始 Current Node。
- Manual Outbound 人工切换成功后只更新持久化的 Current Node，不改变稳定 Node 顺序；具体 selector 字段映射统一在 `7.2 配置生成` 中规定。
- Candidate 优先级只属于 Auto Outbound。Manual Outbound 转为 Auto Outbound 时，在转换页面确认 Candidate 优先级，无需提前为 Manual Node 引入优先级或排序能力。
- 删除原“Manual Node 具有连续、唯一的 1 至 N 优先级并支持人工排序”方案，以本文件后续重写的第 6 章为准。

### `6. Inbound、Outbound 与 Route` 整章重写

- 将本章按“Inbound、Outbound 通用约束、三种 Outbound、Manual/Auto 转换、Route 与级联”重新组织。
- 本章定义业务对象、Node Pool、稳定 Node 顺序、节点角色、Current Node、转换规则和切换时必须达到的业务效果；`outbounds`、`default`、`interrupt_exist_connections` 等 sing-box selector 字段映射统一由 `7.2 配置生成` 规定。
- 第 2 章只保留模型总览和真正需要作为全局不变量的内容。与 Outbound、Route 具体行为重复的规范性要求应尽量由第 6 章唯一规定，避免保留两套语义相同的 REQ。
- 建议使用以下内容整体替换当前第 6 章。

#### 6.1 Inbound

**REQ-INBOUND-001** 系统允许创建任意数量的 Inbound，支持 HTTP、SOCKS、Mixed、Shadowsocks 和 VMess。

**REQ-INBOUND-002** 每个 Inbound 独立定义名称、监听协议、监听地址、监听端口和该协议所需的认证参数。Mixed 在同一端口兼容 HTTP 和 SOCKS。

**REQ-INBOUND-003** 未绑定 Route 的 Inbound 只保存于数据库，不写入 sing-box 配置，也不对外监听。

#### 6.2 Outbound 通用约束

**REQ-OUTBOUND-001** Outbound 分为 Manual Outbound、Auto Outbound 和 Direct Outbound。Manual Outbound 与 Auto Outbound 使用 Node；Direct Outbound 不使用 Node。三类 Outbound 的具体 sing-box 配置映射由 `7.2 配置生成` 统一规定。

**REQ-OUTBOUND-002** Node 是全局对象，可以被多个 Manual Outbound 或 Auto Outbound 复用，但在同一个 Outbound 的 Node Pool 中只能出现一次。

**REQ-OUTBOUND-003** Manual Outbound 和 Auto Outbound 的 Current Node 必须属于各自的 Node Pool。Current Node 发生切换时，必须中断仍绑定旧节点的已有入站连接，使后续重连使用新的 Current Node；实现该业务效果的具体 sing-box 配置字段由 `7.2 配置生成` 统一规定。

#### 6.3 Direct Outbound

**REQ-OUTBOUND-004** Direct Outbound 不包含 Node，不存在 Current Node，不执行节点检测或自动故障切换，流量直接访问目标地址。

#### 6.4 Manual Outbound

**REQ-OUTBOUND-005** Manual Outbound 至少包含一个 Node，不定义 Node 优先级，不执行自动故障切换。新建普通 Outbound 时默认类型为 Manual Outbound。

**REQ-OUTBOUND-006** Manual Outbound 保存自身的稳定 Node 顺序，第一版不提供人工排序。新建 Manual Outbound 时，页面提交的 Node 顺序形成初始稳定顺序；后续新加入的 Node 追加到末尾；删除 Node 后其余 Node 保持原有相对顺序。

**REQ-OUTBOUND-007** 新建 Manual Outbound 时，稳定 Node 顺序中的第一个 Node 成为初始 Current Node。Manual Outbound 的 Current Node 必须持久化，以便重新生成配置或重启后恢复用户最后一次成功选择的 Node。

**REQ-OUTBOUND-008** 用户可以在 sing-box running 时人工切换 Manual Outbound 的 Current Node。只有 Clash API 明确确认切换成功后，系统才持久化新的 Current Node；切换失败时保留原 selector 选择和数据库选择，并在页面提示失败。人工切换不改变 Node 顺序。

**REQ-OUTBOUND-009** Manual Outbound 的 Current Node 被移出但 Node Pool 仍非空时，自动以剩余 Node 中稳定顺序最靠前者作为新的持久化 Current Node；失去全部 Node 时按 `6.8 Route 与级联删除` 删除该 Outbound。

#### 6.5 Auto Outbound

**REQ-OUTBOUND-010** Auto Outbound 至少包含两个不同 Node，其中必须有且只有一个 Fallback Node，并至少有一个 Candidate Node。同一 Node 不能同时承担 Fallback 和 Candidate 角色。

**REQ-OUTBOUND-011** Candidate Node 由用户手工排序。保存后系统生成连续、唯一的 1 至 N 优先级；系统不根据 delay、健康状态或其他指标自动调整该优先级。Fallback Node 不参与 Candidate 排序。

**REQ-OUTBOUND-012** Auto Outbound 的可选 Node 集合由 Fallback Node 和全部 Candidate Node 共同组成。Fallback Node 是独立节点角色，不参与 Candidate 优先级。

**REQ-OUTBOUND-013** Auto Outbound 的 Current Node 完全由后台控制循环管理，用户不能临时人工切换或锁定 Current Node。Auto Outbound 每次实际启动或重启后从 Fallback Node 初始化；该初始选择本身不提供自动故障切换能力。

**REQ-OUTBOUND-014** Route 引用关系决定 Auto Outbound 是否运行后台控制。未被 Route 引用的 Auto Outbound 不运行自动检测、故障切换、Fallback Recovery、Candidate Priority Recovery 或 Fallback 超时重启控制；是否写入 sing-box 配置不改变该规则。

#### 6.6 Manual Outbound 转为 Auto Outbound

**REQ-OUTBOUND-015** 只有 sing-box stopped 时才能转换 Outbound 类型。Manual Outbound 转为 Auto Outbound 前，其现有 Node Pool 必须至少包含两个 Node；不允许在转换过程中从 Node Pool 外另选 Fallback Node，也不允许因转换增加或丢弃 Node。

**REQ-OUTBOUND-016** 用户必须从原 Manual Node Pool 中选择一个 Node 作为 Fallback Node，其余 Node 全部成为 Candidate Node，并在保存转换前确认 Candidate 优先级。原 Manual Current Node 在转换后不保留特殊角色，除非它被选为 Fallback Node。

**REQ-OUTBOUND-017** 转换完成后，所选 Node 成为 Fallback Node，其余 Node 成为按用户确认优先级排列的 Candidate Node。原 Manual 稳定 Node 顺序不再具有业务含义；Auto Outbound 下次启动时从 Fallback Node 初始化。

#### 6.7 Auto Outbound 转为 Manual Outbound

**REQ-OUTBOUND-018** Auto Outbound 转为 Manual Outbound 时，保留原 Fallback Node 和全部 Candidate Node，不允许因转换增加或丢弃 Node。转换后的稳定 Node 顺序为原 Fallback Node 在前，原 Candidate Node 按原优先级顺序在后。

**REQ-OUTBOUND-019** 原 Fallback Node 自动成为转换后 Manual Outbound 的持久化 Current Node；原 Candidate 优先级被移除，不再具有业务含义。用户无需在转换时重新选择 Current Node。

**REQ-OUTBOUND-020** 按 `REQ-OUTBOUND-018` 和 `REQ-OUTBOUND-019` 转换时，系统只转换 ProxyHub 中的 Outbound 类型、节点角色和持久化 Current Node，并清除该 Auto Outbound 的临时控制状态。转换后仍必须执行正常的完整配置生成流程；按 `7.2 配置生成` 的统一映射规则，重新生成的 selector 应与转换前保持等价。

#### 6.8 Route 与级联删除

**REQ-ROUTE-001** Route 只表达一个 Inbound 到一个 Outbound 的映射，不提供规则分流或额外“服务”业务层。每条 Route 必须同时引用一个 Inbound 和一个 Outbound。

**REQ-ROUTE-002** 一个 Inbound 最多被一条 Route 引用；一个 Outbound 可以被零条、一条或多条 Route 引用。多条 Route 引用同一个 Outbound 时，共享该 Outbound 的 Node Pool、Current Node 和运行状态。

**REQ-ROUTE-003** 删除 Inbound 或 Outbound 时，一并删除引用它的 Route。

**REQ-ROUTE-004** 删除 Node 后，从所有 Outbound Node Pool 中删除该 Node 的引用，并按以下规则继续处理：

- Manual Outbound 仍有 Node：按 `REQ-OUTBOUND-009` 保留或重新确定 Current Node；
- Manual Outbound 失去全部 Node：删除该 Outbound；
- Auto Outbound 失去 Fallback Node：删除该 Outbound；
- Auto Outbound 失去全部 Candidate Node：删除该 Outbound；
- Auto Outbound 只删除部分 Candidate Node：保留其余 Candidate 的相对顺序，并重新整理为连续的 1 至 N 优先级；
- 删除 Outbound 后，继续删除引用它的全部 Route。

**REQ-ROUTE-005** 人工删除 Node、删除 Subscription 和订阅刷新删除 Node 都使用相同的级联规则，并在执行前向用户展示完整影响；用户确认后在同一个业务事务中完成 Node、Outbound 和 Route 的变更。

#### 后续同步检查

- 同步更新 `2.1 核心关系`、`2.2 名词` 和 `2.3 全局不变量`，避免 Node Pool、Current Node 和 Route 基数关系与第 6 章形成两套重复的规范性 REQ。第 2 章优先保留模型总览和真正的全局约束，具体 Outbound、Route 行为由第 6 章统一定义。
- 同步更新 `7.1 运行期间允许的修改`：补全 Subscription 新增、修改、删除和刷新均只能在 sing-box stopped 时执行；继续保持 Outbound 类型转换只能在 sing-box stopped 时执行。
- 同步更新 `7.2 配置生成`，并由该节唯一规定配置映射：所有已保存的 Manual/Auto Outbound 均写为 selector，包括未被 Route 引用者；Manual selector 的 `outbounds` 按稳定 Node 顺序包含全部 Manual Node，`default` 为持久化 Current Node；Auto selector 的 `outbounds` 第一项为 Fallback Node，后续为按优先级排列的全部 Candidate Node，`default` 为 Fallback Node；两类 selector 均设置 `interrupt_exist_connections: true`；Direct Outbound 写为 direct outbound。第 7.2 通过引用第 6 章说明这些字段需要达到的业务效果，不再创建语义相同的业务 REQ。
- 同步检查 `8.2 启停与重启`：Manual 恢复持久化 Current Node，Auto 从 Fallback 初始化。
- 同步检查后续故障切换章节中关于 selector 切换后中断已有连接的要求，避免与 `REQ-OUTBOUND-003` 重复定义；后续章节只描述运行时何时切换。
- 如果启用 sing-box cache file，必须避免缓存的 selector 历史选择覆盖上述 Manual `default` 或 Auto Fallback 初始化规则；具体方案留待 sing-box 集成设计确定。
