# 前端日志显示优化方案

## 当前逻辑

### 整体架构
- 纯 HTTP 轮询（无 WebSocket/SSE）
- 后端：内存环形缓冲区 `deque(maxlen=500)` → API `GET /api/logs?since=<index>`
- 前端：每 2 秒 `fetchLogs()` 增量拉取 → `addLog()` 追加 DOM → `saveLogCache()` 写 sessionStorage

### 关键文件
| 角色 | 文件 | 行号 |
|------|------|------|
| 后端日志核心 | `app/logger.py` | 13-103 |
| 后端 API | `app/routes/api_logs.py` | 11-16 |
| 前端 HTML/CSS/JS | `templates/base.html` | 88-114(CSS), 334-340(HTML), 390-506(JS) |

### 后端细节 (`app/logger.py`)
- `WebLogger` 类：`deque(maxlen=500)` + `threading.Lock` 线程安全
- `WebLogger.install()`：替换 `sys.stdout`/`sys.stderr` 拦截所有输出
- `LogWriter`：解析 `[module]` 前缀，空白行不写入
- `get_logs(since)`：根据索引返回增量日志
- 防日志环：werkzeug 日志级别设为 ERROR (`app/routes/__init__.py:28`)

### 前端细节 (`templates/base.html`)
- `logSince`：记录已拉取的最大索引（持久化到 sessionStorage）
- `LOG_MAX = 200`：前端 DOM 最多保留 200 条
- `saveLogCache()`：每追加一条日志就全量序列化 HTML 到 sessionStorage
- `restoreLogCache()`：页面加载时从 sessionStorage 恢复
- `addLog(level, msg, time)`：追加 `<div class="log-line">`，自动滚动到底部
- `escapeHtml()`：用 DOM API 防 XSS
- 日志级别颜色：`info`(灰)、`ok`(绿)、`warn`(橙)、`error`(红)

---

## 可优化点

### 1. 降低轮询开销
- **问题**：切换到其他标签页后仍然 2 秒轮询，浪费请求
- **方案**：用 Page Visibility API 在页面不可见时暂停轮询，切回时立即拉取一次

### 2. DOM 节点过多
- **问题**：日志面板只有 160px 高，DOM 节点只增不减，几百条后滚动性能下降
- **方案**：超过上限（如 300 条）时自动移除最早节点

### 3. sessionStorage 频繁写入
- **问题**：每追加一条日志就全量序列化 200 条 HTML，频繁 I/O
- **方案**：防抖写入，比如 500ms 内最多写一次；或者只存原始数据不存 HTML

### 4. 缺少日志过滤
- **问题**：四种级别全部展示，没有筛选能力
- **方案**：在 log-header 加过滤按钮（info/ok/warn/error），点击切换显示/隐藏

### 5. 缺少日志搜索
- **问题**：无法搜索关键词
- **方案**：加一个搜索输入框，支持关键词高亮

### 6. 轮询错误处理
- **问题**：`fetchLogs()` 失败时没有重试或退避
- **方案**：加指数退避重试，失败后间隔递增（如 2s → 4s → 8s，上限 30s）

### 7. 日志面板高度固定
- **问题**：160px 固定高度，内容多时需要频繁滚动
- **方案**：支持拖拽调整高度，或者双击 header 展开/折叠

### 8. 无后端持久化
- **问题**：服务重启后日志全部丢失
- **方案**：可选写入日志文件（如 rolling file handler），但需要考虑磁盘空间

---

## 优先级建议

| 优先级 | 项目 | 理由 |
|--------|------|------|
| P0 | DOM 节点限制 | 性能问题，影响体验 |
| P0 | sessionStorage 写入优化 | 每行都写，开销大 |
| P1 | Page Visibility 暂停轮询 | 简单改动，明显省流 |
| P1 | 轮询错误重试 | 增加可靠性 |
| P2 | 日志级别过滤 | 提升可用性 |
| P2 | 面板高度可调 | 提升易用性 |
| P3 | 关键词搜索 | 锦上添花 |
| P3 | 后端持久化 | 需要权衡磁盘空间 |
