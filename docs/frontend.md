# ProxyHub v2 — 前端设计文档（桌面端 + 移动端）

> 本文件是前端实现的**唯一依据**。实现时仅参考本文档 + 既有后端代码。
> 状态：⏳ 待审核（2026-08-24）。

---

## 1. 范围与页面清单

### 1.1 桌面端（`templates/`）

| 页面 | 路由 | 功能 |
|------|------|------|
| login | `GET/POST /login` | 用户名密码登录 |
| route（首页） | `GET /` | sing-box 状态 + 服务（入站→出站绑定）列表 + 切节点 |
| inbounds | `GET /inbounds` | 入站监听管理（表格式） |
| outbounds | `GET /outbounds` | 出站/节点池管理 + 池内切节点（卡片式） |
| subscriptions | `GET /subscriptions` | 订阅管理 + 流量 + 关键字过滤 |
| nodes | `GET /nodes` | 节点列表（按订阅分组折叠）+ 延迟检测 |
| settings | `GET /settings` | 设置 + sing-box 升级 + 日志 + 危险区 |

### 1.2 移动端（`templates/mobile/`）

- 单文件 SPA：`templates/mobile/index.html`，路由 `GET /m`。
- 底部标签栏三个视图：**route / inbound / outbound**。
- 只做三件事：**查看状态、手动测速、切换节点**（无任何 CRUD、无设置）。

### 1.3 技术约束

- **纯 HTML/CSS/JS**：无前端框架（无 React/Vue/jQuery）、无构建步骤、**无 static/ 目录**——CSS/JS 全部内联在模板里。
- Jinja2 模板；桌面端继承 `templates/base.html`，移动端为独立文档。
- 所有用户数据渲染前必须 `escapeHtml()`。
- 密码脱敏约定：`GET /api/settings` 返回 `******`；提交时原样回传 `******` 表示不修改；空字符串 `""` 表示禁用认证。
- 后端改造尽量少：只做本文档 §7 列出的增量（认证、页面路由、日志 API、批量当前节点），不改任何现有 API 端点语义。

---

## 2. 设计系统

### 2.1 色彩 / 字体 / 间距

```css
:root {
    --bg-page:        #fafafa;
    --bg-card:        #fff;
    --border:         #e0e0e0;
    --text:           #333;
    --text-secondary: #888;
    --text-disabled:  #bbb;
    --accent:         #1976d2;
    --green:          #4caf50;
    --red:            #e53935;
    --orange:         #ffa726;
    --font:           'Consolas', 'Monaco', 'Courier New', monospace;
    --radius:         4px;
}
```

- 字体基准 14px；小字 11–13px（标签、表头、meta）；标题 14–15px bold。
- 间距：4px（按钮组 gap）/ 8px（卡片内 gap）/ 12px（section padding）/ 16px（卡片间距）/ 20px（模态框 padding）。

### 2.2 组件类（在 base.html / mobile.html 各定义一次）

- **按钮**：`.btn`（28px 高、白底 `#ccc` 边框）、`.btn-sm`、`.btn-primary`（`#333` 深底白字）、`.btn-danger`（红边红字）、`.btn-ok`（绿边绿字）、`.btn-ghost`（无边灰字）、`:disabled`。
- **表单**：`.input`（28px 高、`#fafafa` 底、focus 边框 `#999`）、`textarea.input`、`select.input`、`.field`（label + input）、`.field-row`（flex 行）、`.radio-group`。
- **标签/状态点**：`.tag`（11px 边框小标签，协议/类型标识）；`.status-dot`（6px 圆点）+ `.ok` 绿 / `.error` 红 / `.idle` 灰。
- **卡片**：`.section` / `.section-title`（`#fafafa` 底标题行）/ `.section-body`。
- **模态框**（所有弹窗的统一风格，确认框、表单框（添加节点/入站/出站/服务/订阅）、关键字编辑框、节点选择器等一律使用同一套结构和类，不允许页面自定义弹窗外壳）：`.modal-overlay`（全屏 `#0003`，默认 `display:none`，`.show` 时 flex 居中）/ `.modal`（白底，`min-width:440px; max-width:600px; max-height:85vh`，flex 列布局）/ `.modal-header`（`#fafafa` 底，左侧 `.modal-title` 15px bold + 右侧 ✕ `.modal-close`）/ `.modal-body`（20px padding，滚动区，内用 `.field` 排表单）/ `.modal-footer`（`#fafafa` 底，右对齐按钮，`.btn` 最小宽 72px）。移动端模态框宽度 `min(92vw, 440px)`（表单类弹窗）或底部 sheet（选择器，§6.6）。
  - 确认型：body 一段说明文字，footer = Cancel + 主按钮（危险操作用 `.btn-danger`）。
  - 表单型：body 若干 `.field`，footer = Cancel + Save（`.btn-primary`）。
  - 所有弹窗通过 `classList.add/remove('show')` 开关，✕ 与 Cancel 等效；点击 overlay 空白不关闭（防误触丢失表单）。
- **折叠**：`.collapse-header`（点击切换）+ `.collapse-body`（默认隐藏，`.show` 显示）。**不用箭头图标**：通过标题行底色区分状态——折叠时深色（`#eee` 底 + `.collapsed` 类），展开时浅色（`#fafafa` 底，默认 `.section-title` 样式）。
- **其他**：`.empty-state`（居中灰斜体空状态）、`.lat-pending/.lat-ok/.lat-warn/.lat-bad`（延迟着色）、`.row-flex`（flex 行，行间顶边框）、`.row-active`（当前节点行高亮，浅绿底）、`.error-msg`。

### 2.3 延迟着色规则

| 值 | TCP 列 | URL 列 |
|----|--------|--------|
| 无数据（未测，`null`） | `lat-pending` 灰 `—` | 同左 |
| -1（失败） | `lat-bad` 红 `fail` | 同左 |
| ≤150 / ≤1000 ms | `lat-ok` 绿 | `lat-ok` 绿 |
| ≤300 / ≤2000 ms | `lat-warn` 橙 | `lat-warn` 橙 |
| 更高 | `lat-bad` 红 | `lat-bad` 红 |

---

## 3. 认证

### 3.1 后端流程

```
请求 → auth_required 装饰器
  ├─ web_password 为空 → 放行（直接进入主页）
  ├─ session['authenticated'] = True → 放行
  ├─ API 路由（/api/*）→ 401 JSON {"success": false, "message": "unauthorized"}
  └─ 页面路由 → 302 → /login?next=<原路径>

POST /login（传统表单 POST，非 AJAX）：
  ├─ 比对 settings 的 web_username / web_password
  ├─ 成功 → session['authenticated'] = True → 302 → next（仅允许站内路径）
  └─ 失败 → 重渲染 login.html + {{ error }}
GET /logout → 清 session → 302 → /login
```

### 3.2 登录页

`templates/login.html`：**不继承 base.html**，独立文档：

- 300px 宽白色卡片居中，`<form method="POST" action="/login">`，字段 username + password。
- 错误时服务端渲染 `{{ error }}` 红色文字。
- 含 `<meta name="viewport">`，手机上直接可用——**不做单独的移动登录页**。移动端会话失效同样跳此页（`next=/m`）。

---

## 4. 桌面端

### 4.1 base.html — 应用外壳

所有桌面页面（除 login）继承。flex 全屏固定高度布局：

```
┌──────────────────────────────────────────────┐
│ Navbar (44px)  ProxyHub   [页面操作] [Logout]│
├────────┬─────────────────────────────────────┤
│ Sidebar│  Content (flex:1, overflow-y:auto)  │
│ 200px  │                                     │
├────────┴─────────────────────────────────────┤
│ Status Bar (24px)  ● sing-box version · N nodes │
└──────────────────────────────────────────────┘
```

- **Navbar**：左侧 brand `ProxyHub`；右侧 `{% block navbar_actions %}` + Logout 链接。
- 状态栏：左侧 `status-dot` + `sing-box` 字样 + 版本（`GET /api/status` → `{running, version}`，绿=running 灰=stopped）；右侧 `N nodes`（节点总数）+ `{% block statusbar_right %}`。10 秒轮询 + visibilitychange 立即刷新（§8.2）。
- **无底部日志面板**：操作反馈统一用全局 messageModal / confirmModal（见下）。

**Sidebar 导航**（当前页 `.list-item.active`）：

| 链接 | URL | page 变量 |
|------|-----|-----------|
| route | `/` | `route` |
| inbounds | `/inbounds` | `inbounds` |
| outbounds | `/outbounds` | `outbounds` |
| subscriptions | `/subscriptions` | `subscriptions` |
| nodes | `/nodes` | `nodes` |
| settings | `/settings` | `settings` |

**Jinja2 blocks**：`title` / `navbar_actions` / `extra_css` / `content` / `statusbar_right` / `modals` / `extra_js`。

**全局模态框**（base.html 内置两个）：
- `confirmModal`：`showConfirm(title, msg, onConfirm, confirmLabel)` 驱动，OK 按钮绑定回调。
- `messageModal`：`showMessage(msg)` 驱动，单 OK 按钮。

**全局 JS**（子页面直接用）：
- `escapeHtml(text)` — 只定义一次。
- `closeModal(id)` / `showMessage(msg)` / `showConfirm(...)`。
- `api(path, method, body)` — fetch 封装：自动 `Content-Type: application/json`；**401 时跳 `/login?next=<当前路径>`**；返回解析后的 JSON。
- `checkSingboxStatus()` — 状态栏轮询（10s），并挂 `visibilitychange` 监听（§8.2）。
- **统一页面数据流 `loadPageData()`**：每页入口函数（§8.3 缓存策略）——先渲染 localStorage 缓存（秒开），再拉真实数据更新；随后启动 10s 轮询 + `visibilitychange` 立即刷新。子页面只需实现 `fetchData()` + `render(data)`。
- **移动端重定向**：`matchMedia('(max-width: 768px)')` 命中时 `location.replace('/m')`（`/m` 不反向跳转，移动端顶部菜单可手动切回桌面）。

### 4.2 route 页（`GET /`，首页）

**作用**：总览运行状态 + 管理"服务"（入站→出站绑定）+ 手动切节点。

内容分区：

1. **sing-box 状态卡**（一个 `.section`）：
   - 状态点 + 版本 + 运行状态；按钮 `Start` / `Stop` / `Restart`（`POST /api/start|stop|restart`）。
2. **服务列表**（每服务一个 `.section` 卡片，10s 轮询 + visibilitychange 立即刷新，§8.2）：

```
┌────────────────────────────────────────────────────┐
│ ● svc-name   :8388 (ss)              [✎][✕]        │
│   inbound: my-ss · outbound: auto-pool             │
│   current node: 香港-01                            │
│   [switch node]  [stop]                            │
└────────────────────────────────────────────────────┘
```

- 状态与当前节点：`GET /api/services/current-nodes`（§7.5）一次拉全量；`status: running` 绿点，`stopped`/`direct` 灰点。
- `current_node` 形如 `n{id}`——前端映射成节点名显示（§6.5）；`direct` 原样显示。
- **switch**：弹模态框列出该服务出站的池节点（含延迟着色），点击即 `POST /api/services/<id>/switch {node_id}`。
- **start/stop**：`POST /api/services/<id>/start|stop`（start = 切到池首节点，stop = 切到 direct）。
- **新建/编辑**：模态框 = name + inbound 下拉（`GET /api/inbounds`）+ outbound 下拉（`GET /api/outbounds`，含 `direct` 项 id=0）+ auto_start 复选框 → `POST/PUT /api/services[/id]`。
- **删除**：showConfirm → `DELETE /api/services/<id>`。
- navbar_actions：`+ New Service`。
- 空状态：无入站/出站时提示先去对应页面创建。

### 4.3 inbounds 页

表格式：

```
 name │protocol│listen        │params        │actions
 my-ss│[ss]    │0.0.0.0:8388  │aes-256-gcm   │[✎][✕]
```

- 数据源 `GET /api/inbounds`；协议用 `.tag` 显示；params 列摘要展示 `params_json`（username / method / uuid 前 8 位等）。
- 新建/编辑模态框按协议自适应字段：

| 协议 | 参数字段 |
|------|---------|
| http / socks | username, password（可空 = 无认证） |
| ss | method（下拉：aes-256-gcm / aes-128-gcm / chacha20-ietf-poly1305 / 2022-blake3-aes-256-gcm）, password |
| vmess | uuid, alterId, transport(tcp/ws/h2/grpc) + 动态子字段（ws: path/host；h2: host/path；grpc: service_name） |

- 公共字段：name、protocol（下拉：http/socks/ss/vmess）、listen_addr（默认 0.0.0.0）、port。
- 提交：字段拼装为 `params_json` JSON 字符串 → `POST/PUT /api/inbounds[/id]`。删除走 showConfirm。
- 保存后 showMessage 提醒：需在 route 页 Restart sing-box 生效。

### 4.4 outbounds 页

卡片式，每张卡片一个出站：

```
┌──────────────────────────────────────────────────┐
│  auto-pool · 3 nodes                [✎][✕]       │ ← 浅色标题行 = 展开（深色 = 折叠）
│ # │name   │protocol│addr:port    │tcp │url │act  │
│ 1 │node-a │vmess   │1.2.3.4:443  │45ms│200 │⇄ ▲▼✕│ ← 当前节点行 .row-active
│ 2 │node-b │ss      │5.6.7.8:8388 │150 │ —  │⇄ ▲▼✕│
│ [+ add node]                                     │
└──────────────────────────────────────────────────┘
```

**数据模型**：出站只有 `name` + 节点池（`GET /api/outbounds` 每项含 `pool[]`，池条目含 `id`（池条目 id）、`node_id`、`priority` 及节点详情 JOIN）。direct 哨兵（id=0）不出现在此页（后端已过滤）。

- **新建/编辑模态框** = name + 节点选择器（filter 输入框 + 节点列表点击切换选中，选中集合即池、点击顺序即优先级）。保存流程：`POST/PUT /api/outbounds[/id]` → `POST /api/outbounds/<id>/nodes/reorder {node_ids:[...]}` 全量同步池。
- **池内操作**：
  - ▲▼ 调序：本地交换后调 reorder（全量 `node_ids`）。
  - ✕ 移除：`DELETE /api/outbounds/<id>/nodes/<pool_id>`。
  - `+ add node`：弹节点选择器，已在池中的灰显不可选 → `POST /api/outbounds/<id>/nodes {node_id}`。
  - 首节点（priority 最小）显示 `默认` tag。
- **当前节点**：`GET /api/services/current-nodes`（§7.5）得出每出站当前 `n{id}`，对应行 `.row-active` 高亮；非当前节点显示 ⇄ 切换按钮——点击后对该出站的所有绑定服务逐个 `POST /api/services/<id>/switch`；无服务绑定此出站时 showMessage 提示。
- 每行单节点测速按钮 ↻（§6.3 单节点同步流程）。
- 折叠状态存 localStorage（`ph_ui_*`，§8.3）。

### 4.5 subscriptions 页

订阅卡片列表：

```
┌──────────────────────────────────────────────────┐
│ sub-name · N nodes  [updated: ...]  [↻][✎][✕]    │
│ Traffic: 1.2 GB / 5.0 GB — 3.8 GB remaining      │
│ Expires: 2026-07-15 (23 days)                    │
│ filter  │ click to set filter keywords           │
│ exclude │ click to set exclude keywords          │
└──────────────────────────────────────────────────┘
```

- 数据源 `GET /api/subscriptions`；节点数来自 `GET /api/nodes/by-sub/<id>` 或 grouped 数据。
- 头部操作：刷新 `POST /api/subscriptions/<id>/refresh`（刷新中按钮禁用）、编辑（name/url）、删除（showConfirm）。
- 流量行：`formatBytes()`（B→KB→MB→GB，1 位小数）；`remaining = total - upload - download`；`expire_at`（unix 秒）转日期 + 剩余天数；`total_bytes=0` 时不显示流量行。
- 关键字编辑模态框：textarea 每行一个关键字 → `PUT /api/subscriptions/<id>` 只提交 `{filter_keywords}` 或 `{exclude_keywords}`；保存后提示需点刷新生效。
- navbar_actions：`+ New Subscription`（name + url 模态框 → `POST /api/subscriptions`）。

### 4.6 nodes 页

按订阅分组的折叠列表：

```
┌──────────────────────────────────────────────────┐
│  sub-name · N nodes               [check all]    │ ← 深色 = 折叠
│  sub-name · N nodes               [check all]    │ ← 浅色 = 展开（下方显示节点行）
│ name │protocol│address:port │tcp │url │actions   │
│ ...                                   │↻ ✎ ✕     │
└──────────────────────────────────────────────────┘
navbar_actions: [Check All] [+ New Node]
```

- 数据源 `GET /api/nodes/grouped`（`groups[] = {sub|null, nodes[]}`，`sub=null` 组显示为 Custom Nodes）。
- 延迟列：§6.3 统一策略。
- **检测**：
  - 单节点 ↻：`POST /api/nodes/check {node_id}` —— 同步返回 `{single:true, result:{tcp_latency_ms, url_latency_ms, error}}`，直接更新行。
  - 组 check all / 顶部 Check All：`POST /api/nodes/check {sub_id}` 或 `{}` —— 异步返回 `{task_id}`，每 1s 轮询 `GET /api/nodes/check/<task_id>`，按 `results` 逐行更新，`status=done` 停止。
- **节点编辑模态框**（协议自适应；`config_json` 字段名以 `app/parser/` 输出为准，实现时对照 parser 源码核对）：
  - **URL 导入区**：粘贴 `vmess://` `vless://` `ss://` `trojan://` `hy2://` `tuic://` 链接，前端 JS 解析回填（vmess = base64 JSON；ss 支持 SIP002/legacy + plugin 参数；其余按 `proto://userinfo@host:port?query#name` 解析）。
  - 基础字段：name、protocol 下拉（vmess/vless/trojan/ss/hysteria2/tuic）、address、port。
  - 协议字段（按 protocol 动态显示）：
    - vmess: uuid(id)、alterId(aid)、security、network(tcp/ws/h2/grpc)+子字段、tls/sni/allowInsecure/alpn/fingerprint
    - vless: uuid(id)、flow、encryption、network+子字段、reality_public_key/reality_short_id、tls 同上
    - trojan: password、sni、alpn、allowInsecure、network+子字段
    - ss: method、password、plugin（仅 obfs-local）、plugin_opts
    - hysteria2: password、sni、allowInsecure、obfs、obfs_password、up_mbps、down_mbps
    - tuic: uuid、password、sni、allowInsecure、alpn、congestion_control、udp_relay_mode
  - 提交：字段拼装为 `config_json` JSON 字符串 → `POST/PUT /api/nodes[/id]`。
- 删除节点走 showConfirm → `DELETE /api/nodes/<id>`。

### 4.7 settings 页

分区（每区一个 `.section`）：

1. **sing-box**：当前版本（`GET /api/status`）；`Check Update`（`GET /api/upgrade/status` → 显示 current/latest/has_update）；`Download Update`（`POST /api/upgrade/download`，下载期间按钮禁用 + 轮询 `/api/upgrade/status` 的 state 直到 done/error）。
2. **Node check**：check_interval_normal、check_interval_failover、tcp_timeout、curl_timeout、test_url。
3. **Clash API**：clash_api_port。
4. **Web UI**：web_port、web_username（这两个直接保存）；**密码单独操作**，用两个按钮：
   - `Clear Password`：弹确认框，**需输入 `CLEAR` 确认**（输入框值匹配才允许点确认）→ `POST /api/settings {web_password: ""}` → 提示认证已禁用。
   - `Change Password`：弹表单框（current password（已认证会话可不校验，直接覆盖）、new password、confirm new password，两次一致才提交）→ `POST /api/settings {web_password: "<new>"}`。
   - 设置表单区不再出现 password 输入框；`GET /api/settings` 返回的 `******` 只用于显示"已设置"状态。
5. **Logs**（§5）：
   - `<pre>` 等宽只读滚动区显示当前日志末尾 200 行（`GET /api/logs?tail=200`，进入页面时加载一次 + 手动 `Refresh` 按钮，**不自动轮询**）。
   - **`Download Log` 按钮**放此 section 头部右侧（`GET /api/logs/download`，浏览器直接下载）。
6. **Danger zone**：`Clear All Nodes`（showConfirm → `POST /api/nodes/clear`）。

保存交互：每 section 一个 Save 按钮 → `POST /api/settings` 只提交该 section 的键值；密码未改时提交 `******`。修改 web_port / clash_api_port 后提示重启生效。

---

## 5. 日志

### 5.1 现状

`app/logger.py` 已把每次进程启动的日志写入 `logs/YYYY-MM-DD_HHMMSS.log`。当前进程日志文件 = `settings.LOGS_DIR` 下 mtime 最新的 `*.log`。

### 5.2 新增 API（后端，最简实现）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/logs?tail=N` | 返回当前日志文件末尾 N 行（默认 200，上限 1000）：`{file: "2026-08-24_101500.log", lines: [...]}`；无文件时 `{file: null, lines: []}` |
| GET | `/api/logs/download` | 当前日志文件作为附件下载（`send_file(..., as_attachment=True)`）；无文件 404 |

实现：取 LOGS_DIR 下 mtime 最新的 `*.log`；tail 直接读全部行取末尾 N 行（文件很小，不做偏移优化）。不做实时推送、不做增量拉取。

### 5.3 前端

仅 settings 页 Logs section（§4.7-5）。日志行为纯文本，前端 `escapeHtml` 后逐行渲染进 `<pre>`。

---

## 6. 移动端（iOS/Android 浏览器）

### 6.1 形态

- **单文件 SPA**：`templates/mobile/index.html`，路由 `GET /m`；不继承桌面 base.html。同一套 CSS 变量，组件按移动端重写：点击目标 ≥40px、底部标签栏 56px、内容区全宽 padding 12px。
- 底部标签栏三个视图：**route / inbound / outbound**；JS 切换无跳转，hash `#route|#inbound|#outbound` 记忆当前视图（刷新后恢复）。
- 顶部栏：标题 `ProxyHub` + sing-box 状态点；右上角菜单放 `Desktop`（跳 `/`）和 `Logout`。
- 只读为主，无任何 CRUD / 设置 / 订阅节点管理。
- 所有请求走与桌面相同的 `/api/*`；401 跳 `/login?next=/m`。

### 6.2 route 视图（首页）

- sing-box 状态卡：状态点 + version + Start/Stop/Restart 大按钮。
- 服务列表卡（10s 轮询 `GET /api/services` + `GET /api/services/current-nodes`，visibilitychange 立即刷新）：每项显示 服务名、入站协议:端口、当前节点名、状态点。
- 每项操作：`⇄ switch`（底部 sheet 列出池节点，点选即 `POST /api/services/<id>/switch`）、`stop`/`start`。
- 顶部下拉刷新或刷新按钮。

### 6.3 inbound 视图（查看状态）

- 入站卡片列表：name、协议 tag、listen:port、参数摘要（同桌面 params 列）。
- 纯查看，无编辑。

### 6.4 outbound 视图（测速 + 切节点）

- 出站卡片列表（折叠）：池节点行显示 name、协议、tcp/url 延迟（着色）、当前节点高亮。
- 行操作：`⇄ 切换`（对该出站所有绑定服务 switch，同桌面 §4.4）、`↻ 测速`（单节点同步检测）。
- 卡片头部：`check all`（批量异步 + 1s 轮询进度，同桌面 §4.6）。
- 当前节点：`GET /api/services/current-nodes`；延迟：`GET /api/nodes/<id>/latency`（§6.3-of-§7 统一策略，见 §6.6）。

### 6.5 当前节点 / tag 映射（桌面移动通用）

- `current_node` / `node_tag` 形如 `n{id}`、`g{id}`、`direct`。前端统一用正则 `^n(\d+)$` 提取节点 id 后从节点列表映射显示名；`direct` 原样显示；`null` 显示 `—`。

### 6.6 移动端实现注意

- 模态框用底部 sheet 样式：`position:fixed; left:0; right:0; bottom:0;` 上圆角，操作按钮全宽大号。
- 无 hover 态；状态用颜色 + 文字双标识。
- localStorage 只存视图 hash / 折叠状态，不存敏感信息。

---

## 7. 后端配套改动清单（前端所需的最小后端增量）

> 现有 API 端点语义一律不变，以下为新增。

### 7.1 应用工厂（`app/__init__.py`）

- `app.secret_key`：优先读环境变量 `PROXYHUB_SECRET`；否则读 `data/secret_key` 文件，不存在则生成 32 字节随机值写入（0600 权限）——重启后会话不失效。
- 注册页面蓝图（新增 `app/pages.py`）。
- 移动端模板渲染 `mobile/index.html`（Flask 默认 template_folder 即 `templates/`，直接 `render_template('mobile/index.html')`）。

### 7.2 认证（新增 `app/auth.py`）

- `@auth_required` 装饰器：§3.1 流程。
- `GET/POST /login`、`GET /logout` 路由。
- 所有页面路由与 `/api/*` 统一挂认证（蓝图 `before_request` 实现）。
- `next` 参数仅允许以 `/` 开头的站内路径（防开放重定向）。

### 7.3 页面路由（新增 `app/pages.py`）

| 路由 | 渲染 |
|------|------|
| `GET /` | `route.html`（page='route'） |
| `GET /inbounds` | `inbounds.html` |
| `GET /outbounds` | `outbounds.html` |
| `GET /subscriptions` | `subscriptions.html` |
| `GET /nodes` | `nodes.html` |
| `GET /settings` | `settings.html` |
| `GET /m` | `mobile/index.html` |

均挂认证；模板只传 `page` 变量，数据全部前端拉 API。

### 7.4 日志 API（加到 `app/routes.py`）

- `GET /api/logs?tail=N`、§5.2。
- `GET /api/logs/download`、§5.2。

### 7.5 批量当前节点 API（加到 `app/routes.py`）

- `GET /api/services/current-nodes`：遍历 `db_service.list_all()`，每个服务取 `outbound_id`，非 0 时调 `clash.get_proxy_now(f'g{oid}')`，返回：
  ```json
  {"services": [{"id": 1, "outbound_id": 2, "current_node": "n42", "status": "running"}]}
  ```
  - outbound_id=0 → `{"current_node": "direct", "status": "direct"}`
  - clash 不可达 → `{"current_node": null, "status": "stopped"}`
- 目的：route/outbounds/移动端一次拉全量，避免 N+1 次单服务查询。保留已有 `GET /api/services/<id>/status` 单服务端点。

### 7.6 不做清单（明确排除）

- 不做内存日志收集器 / 实时日志推送 / 底部日志面板。
- 不做 Start All / Shutdown / 系统信息 API。
- 不做 scheduler（自动 failover）的界面配置（沿用 settings 里的间隔参数）。
- 不改 sing-box 编排、checker、parser、db 任何既有逻辑。

---

## 8. 前端通用约定

### 8.1 数据流与反馈

1. **操作反馈**：成功/失败用 `showMessage()`；危险/不可逆操作用 `showConfirm()`。
2. **401 处理**：`api()` 封装统一跳登录（带 `next`）。
3. **延迟数据统一策略**：节点渲染后，对可见节点并发 `GET /api/nodes/<id>/latency` 填充（`Promise.all`）；检测完成后重新拉一次。`null` → `—`，`-1` → `fail`，着色按 §2.3。
4. **escapeHtml** 用于一切用户可控字符串（节点名、订阅名、服务名、日志行）。

### 8.2 轮询与切回页面立即刷新

- 周期：状态栏 / route 页服务列表 / 移动端 route 视图等定时数据统一 **10s** 轮询；检测进度 1s 轮询。
- **切回页面立即刷新**：所有轮询点同时挂 `document.addEventListener('visibilitychange', ...)`——`document.visibilityState === 'visible'` 时立刻执行一次同样的拉取（不等下一个周期）。移动端 browser 切换 tab / 切后台再回来同样生效。

### 8.3 本地缓存秒开（localStorage）

目标：切换页面或刷新时先渲染本地缓存，拿到真实数据后再更新，消除白屏等待。

```
页面加载
  1. 同步读 localStorage['ph_cache_<page>'] → 有则立即 render(cached)（标注为旧数据，不禁用操作）
  2. 异步 fetchData() → render(real) → 写 localStorage['ph_cache_<page>']（覆盖）
  3. fetch 失败 → 保留缓存渲染 + showMessage 提示
```

- **缓存内容**：每页的主体列表数据（route：services + current-nodes + status；inbounds/outbounds/subscriptions/nodes：各自列表 + 延迟快照；settings：settings 字典 + sing-box 版本）。
- **UI 状态另存**：折叠/展开状态（nodes 分组、outbounds 卡片、移动端出站卡片）、移动端当前视图 hash，独立 key（如 `ph_ui_collapse`），不进数据缓存。
- **key 规范**：`ph_cache_<page>` / `ph_ui_*`；**不存任何敏感信息**（密码、订阅 URL 之外的密钥字段）；写入前序列化 JSON，读失败按无缓存处理。
- **数据变更即失效**：本页内任何增删改/切换/测速成功后，用最新响应重写对应缓存，保证下次进入所见即最新。
- 登出时清空全部 `ph_cache_*`（前端 `localStorage.clear()` 或按前缀删除）。

---

## 9. 文件清单（交付物）

```
app/
  __init__.py        # 改：secret_key + 注册页面蓝图
  auth.py            # 新：auth_required + login/logout
  pages.py           # 新：页面路由（含 /m）
  routes.py          # 改：+ /api/logs、/api/logs/download、/api/services/current-nodes
templates/
  base.html          # 重写：设计系统 + 外壳（navbar/sidebar/status bar/全局模态框/全局 JS）
  login.html         # 新
  route.html         # 新
  inbounds.html      # 新
  outbounds.html     # 新
  subscriptions.html # 新
  nodes.html         # 新
  settings.html      # 新（含 Logs section + Download 按钮）
  mobile/
    index.html       # 新：单文件 SPA，route/inbound/outbound 三视图
```

## 10. 实现顺序

1. 后端增量：auth + pages + logs API + current-nodes API（§7）。
2. `base.html` + `login.html` + `route.html`（跑通外壳 + 首页）。
3. `inbounds` / `outbounds` / `subscriptions` / `nodes`。
4. `settings`（含日志）。
5. `mobile/index.html`。
6. 端到端自测：空密码直通、登录/登出、401 跳转、各页 CRUD、检测轮询、切节点、移动视图。
