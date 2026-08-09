# ProxyHub 重建设计文档

> 本文档用于指导 Claude 完整重建 ProxyHub 项目。
> 目标平台：**仅 Ubuntu 22.04+ (amd64)**。

---

## 一、项目概述

ProxyHub 是一个自托管的代理服务管理面板，提供 Web UI 统一管理多个代理引擎的入站、出站、订阅和节点，支持节点健康检测。

### 核心功能
1. **订阅管理** — 解析 `vmess://`、`ss://` 链接和 Clash YAML 格式，支持关键字过滤
2. **节点管理** — 批量 TCP/HTTP 延迟检测，自定义节点，按订阅分组
3. **入站管理** — 定义本地监听（HTTP/SOCKS5/Shadowsocks/VMess）
4. **出站管理** — 定义出口策略（单节点 / 自动故障转移节点池）
5. **服务管理** — 组合入站+出站，启动实际的代理进程（Xray/sslocal/sing-box）
6. **二进制升级** — 从 GitHub Releases 下载最新代理引擎
7. **实时日志** — Web 端日志面板
8. **会话认证** — 用户名/密码登录

### 涉及的外部代理引擎
| 引擎 | GitHub 仓库 | 用途 |
|------|-----------|------|
| Xray | XTLS/Xray-core | VMess/VLESS/Trojan/Shadowsocks/HTTP/SOCKS |
| sslocal | shadowsocks/shadowsocks-rust | Shadowsocks + obfs 插件 |
| sing-box | SagerNet/sing-box | Hysteria2 / TUIC |

---

## 二、项目结构

```
ProxyHub/
├── setup.sh                 # 一键部署脚本
├── run.py                   # 应用入口
├── requirements.txt         # Python 依赖
│
├── docs/                    # 项目文档
│   ├── design/              # 设计文档
│   │   ├── DESIGN.md        # 本设计文档
│   │   ├── failover.md      # 出站节点自动故障切换
│   │   └── fallback-node.md # Pool 首节点备选机制
│   └── todo/                # 待优化项
│       ├── failover-phase3-optimization.md
│       ├── log-optimization.md
│       └── health-check-refactor.md
│
├── app/
│   ├── __init__.py          # Flask 应用工厂
│   ├── settings.py          # 配置常量与默认值
│   │
│   ├── models/              # 数据访问层 (SQLite)
│   │   ├── __init__.py
│   │   ├── database.py      # 连接管理、初始化、迁移
│   │   ├── setting.py       # 设置 CRUD
│   │   ├── subscription.py  # 订阅 CRUD
│   │   ├── node.py          # 节点 CRUD
│   │   ├── inbound.py       # 入站 CRUD
│   │   ├── outbound.py      # 出站 + 节点池 CRUD
│   │   └── service.py       # 服务 CRUD
│   │
│   ├── services/            # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── auth_service.py       # 登录/登出/密码验证
│   │   ├── subscription_service.py  # 订阅获取、解析、过滤、入库
│   │   ├── node_service.py       # 节点验证、健康检测编排
│   │   ├── outbound_service.py   # 出站创建/更新 + 节点池管理
│   │   ├── service_manager.py    # 服务启动/停止/重启/auto-start
│   │   ├── upgrade_service.py    # 二进制版本检查/下载
│   │   └── config_service.py     # 配置文件生成（临时 + 持久化）
│   │
│   ├── engine/              # 代理引擎配置生成
│   │   ├── __init__.py      # 调度器: 根据 bin_type 分发
│   │   ├── xray.py          # Xray JSON 配置生成
│   │   ├── sslocal.py       # sslocal JSON 配置生成
│   │   └── singbox.py       # sing-box JSON 配置生成
│   │
│   ├── process/             # 进程管理
│   │   └── manager.py       # 启动/停止/重启/状态/版本/PID管理
│   │
│   ├── checker/             # 节点健康检测
│   │   ├── __init__.py      # 编排层：TCP ping + URL test
│   │   └── script.py        # 调用 scripts/test.sh 的子进程封装
│   │
│   ├── routes/              # Flask 路由（薄层，无业务逻辑）
│   │   ├── __init__.py      # 注册所有蓝图
│   │   ├── pages.py         # 页面路由 (/dashboard, /login 等)
│   │   ├── api_settings.py  # /api/settings/*
│   │   ├── api_auth.py      # /api/auth/*
│   │   ├── api_subscriptions.py  # /api/subscriptions/*
│   │   ├── api_nodes.py     # /api/nodes/*
│   │   ├── api_inbounds.py  # /api/inbounds/*
│   │   ├── api_outbounds.py # /api/outbounds/*
│   │   ├── api_services.py  # /api/services/*
│   │   ├── api_bins.py      # /api/bins/*
│   │   ├── api_upgrade.py   # /api/upgrade/*
│   │   ├── api_logs.py      # /api/logs
│   │   └── api_system.py    # /api/system/*
│   │
│   ├── utils/               # 工具函数
│   │   ├── __init__.py
│   │   ├── helpers.py       # format_size, split_keywords
│   │   └── validators.py    # 协议/端口/bin_type 验证
│   │
│   └── logger.py            # Web 端日志收集器
│
├── templates/               # Jinja2 模板 (保持现有)
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── subscriptions.html
│   ├── nodes.html
│   ├── inbounds.html
│   ├── outbounds.html
│   ├── services.html        # (目前缺失，需新建)
│   └── settings.html
│
├── static/                  # 静态资源 (CSS/JS)
│   └── (如有需要从模板中提取)
│
├── scripts/
│   └── test.sh              # 节点连通性测试脚本 (bash)
│
├── bin/                     # 代理二进制存放 (gitignored)
├── config/                  # 服务运行时配置 (gitignored)
└── data/                    # SQLite 数据库 + PID 文件 (gitignored)
```

---

## 三、数据模型

### 数据库：SQLite，文件 `data/proxyhub.db`

### 3.1 表结构

```sql
-- 设置表
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 订阅表
CREATE TABLE subscriptions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    url              TEXT NOT NULL,
    filter_keywords  TEXT DEFAULT '',
    exclude_keywords TEXT DEFAULT '',
    updated_at       TEXT,                    -- ISO 时间戳
    upload_bytes     INTEGER DEFAULT 0,
    download_bytes   INTEGER DEFAULT 0,
    total_bytes      INTEGER DEFAULT 0,
    expire_at        INTEGER DEFAULT 0
);

-- 节点表 (sub_id=0 表示用户自定义节点)
CREATE TABLE nodes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sub_id        INTEGER DEFAULT 0,
    name          TEXT NOT NULL,
    protocol      TEXT NOT NULL,              -- vmess/vless/trojan/ss/ssr/hysteria2/tuic/anytls
    address       TEXT NOT NULL,
    port          INTEGER NOT NULL,
    config_json   TEXT NOT NULL,              -- 协议相关参数 JSON
    bin_type      TEXT DEFAULT 'xray',        -- xray / sslocal / sing-box
    tcp_latency   INTEGER,                    -- TCP 延迟 (ms)
    curl_latency  INTEGER,                    -- HTTP 延迟 (ms)
    last_check_at TEXT                       -- 最后检测时间 ISO
);

-- 入站表
CREATE TABLE inbounds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    protocol    TEXT NOT NULL,                -- http / socks / ss / vmess
    listen_addr TEXT DEFAULT '0.0.0.0',
    port        INTEGER NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}'    -- method/password/id/aid 等
);

-- 出站表
CREATE TABLE outbounds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,                -- 'single' 或 'auto'
    config_json TEXT NOT NULL DEFAULT '{}'    -- {node_id: N} 或 {check_interval, test_url}
);

-- 出站节点池关联表 (仅 auto 类型使用)
CREATE TABLE outbound_nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    outbound_id INTEGER NOT NULL,
    node_id     INTEGER NOT NULL,
    priority    INTEGER DEFAULT 0
);

-- 服务表
CREATE TABLE services (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    inbound_id  INTEGER NOT NULL,
    outbound_id INTEGER NOT NULL,
    status      TEXT DEFAULT 'stopped',       -- stopped / running / error
    auto_start  INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);
```

### 3.2 默认设置

```python
DEFAULT_SETTINGS = {
    'bin_path_xray':        './bin/xray',
    'bin_path_sslocal':     './bin/sslocal',
    'bin_path_singbox':     './bin/sing-box',
    'config_dir':           './config',
    'check_interval_normal': '240',    # 正常检测间隔(秒)
    'check_interval_failover': '30',   # 故障转移检测间隔(秒)
    'tcp_timeout':           '3',
    'curl_timeout':          '5',
    'test_url':              'http://www.gstatic.com/generate_204',
    'web_port':              '8080',
    'web_username':          'admin',
    'web_password':          '',        # 空 = 无需认证
}
```

---

## 四、路由设计

### 4.1 页面路由 (Blueprint: pages)

| 方法 | 路径 | 处理函数 | 说明 |
|------|------|---------|------|
| GET | `/` | `index` | 重定向到 `/dashboard` |
| GET | `/dashboard` | `dashboard` | 仪表盘 |
| GET | `/inbounds` | `inbounds_page` | 入站管理页 |
| GET | `/outbounds` | `outbounds_page` | 出站管理页 |
| GET | `/subscriptions` | `subscriptions_page` | 订阅管理页 |
| GET | `/nodes` | `nodes_page` | 节点管理页 |
| GET | `/settings` | `settings_page` | 设置页 |
| GET/POST | `/login` | `login_page` | 登录页 |
| GET | `/logout` | `logout` | 登出 |

### 4.2 设置 API (Blueprint: api_settings, 前缀 `/api/settings`)

| 方法 | 路径 | 处理函数 | 说明 |
|------|------|---------|------|
| GET | `/` | `get_settings` | 获取所有设置（密码脱敏） |
| POST | `/` | `update_settings` | 批量更新设置 |
| POST | `/reset` | `reset_settings` | 重置为默认值 |

### 4.3 二进制 API (Blueprint: api_bins, 前缀 `/api/bins`)

| 方法 | 路径 | 处理函数 | 说明 |
|------|------|---------|------|
| GET | `/status` | `get_bins_status` | 获取所有二进制状态 |

### 4.4 升级 API (Blueprint: api_upgrade, 前缀 `/api/upgrade`)

| 方法 | 路径 | 处理函数 | 说明 |
|------|------|---------|------|
| GET | `/check/<bin_name>` | `check_upgrade` | 检查更新 |
| POST | `/download/<bin_name>` | `download_upgrade` | 下载更新 |

### 4.5 订阅 API (Blueprint: api_subscriptions, 前缀 `/api/subscriptions`)

| 方法 | 路径 | 处理函数 | 说明 |
|------|------|---------|------|
| GET | `/` | `list_subscriptions` | 列表（含节点数量） |
| POST | `/` | `create_subscription` | 创建 |
| PUT | `/<int:id>` | `update_subscription` | 更新 |
| DELETE | `/<int:id>` | `delete_subscription` | 删除 |
| POST | `/<int:id>/refresh` | `refresh_subscription` | 刷新解析节点 |

### 4.6 节点 API (Blueprint: api_nodes, 前缀 `/api/nodes`)

| 方法 | 路径 | 处理函数 | 说明 |
|------|------|---------|------|
| GET | `/` | `list_nodes` | 所有节点 |
| GET | `/grouped` | `list_nodes_grouped` | 按订阅分组 |
| GET | `/by-sub/<int:sub_id>` | `list_nodes_by_sub` | 某订阅的节点 |
| POST | `/` | `create_node` | 创建自定义节点 |
| PUT | `/<int:id>` | `update_node` | 更新节点 |
| DELETE | `/<int:id>` | `delete_node` | 删除节点 |
| POST | `/clear` | `clear_nodes` | 清空所有节点 |
| POST | `/check` | `check_nodes` | 检测节点连通性 |
| GET | `/check/<task_id>/status` | `check_status` | 查询检测进度 |

### 4.7 入站 API (Blueprint: api_inbounds, 前缀 `/api/inbounds`)

| 方法 | 路径 | 处理函数 | 说明 |
|------|------|---------|------|
| GET | `/` | `list_inbounds` | 列表 |
| POST | `/` | `create_inbound` | 创建 |
| PUT | `/<int:id>` | `update_inbound` | 更新 |
| DELETE | `/<int:id>` | `delete_inbound` | 删除 |

### 4.8 出站 API (Blueprint: api_outbounds, 前缀 `/api/outbounds`)

| 方法 | 路径 | 处理函数 | 说明 |
|------|------|---------|------|
| GET | `/` | `list_outbounds` | 列表（含节点池和节点详情） |
| POST | `/` | `create_outbound` | 创建 |
| PUT | `/<int:id>` | `update_outbound` | 更新 |
| DELETE | `/<int:id>` | `delete_outbound` | 删除 |
| GET | `/<int:id>/nodes` | `get_pool_nodes` | 获取节点池 |
| POST | `/<int:id>/nodes` | `add_pool_node` | 添加节点到池 |
| DELETE | `/<int:id>/nodes/<int:pool_id>` | `remove_pool_node` | 从池移除节点 |
| POST | `/<int:id>/nodes/reorder` | `reorder_pool_nodes` | 重排节点优先级 |

### 4.9 服务 API (Blueprint: api_services, 前缀 `/api/services`)

| 方法 | 路径 | 处理函数 | 说明 |
|------|------|---------|------|
| GET | `/` | `list_services` | 列表 |
| GET | `/<int:id>` | `get_service` | 详情 |
| POST | `/` | `create_service` | 创建 |
| PUT | `/<int:id>` | `update_service` | 更新 |
| DELETE | `/<int:id>` | `delete_service` | 删除 |
| POST | `/<int:id>/start` | `start_service` | 启动服务 |
| POST | `/<int:id>/stop` | `stop_service` | 停止服务 |
| POST | `/<int:id>/restart` | `restart_service` | 重启服务 |

### 4.10 日志 API (Blueprint: api_logs, 前缀 `/api/logs`)

| 方法 | 路径 | 处理函数 | 说明 |
|------|------|---------|------|
| GET | `/` | `get_logs` | 获取日志 (query: `?since=N`) |

### 4.11 系统 API (Blueprint: api_system, 前缀 `/api/system`)

| 方法 | 路径 | 处理函数 | 说明 |
|------|------|---------|------|
| GET | `/info` | `system_info` | 数据库大小、二进制状态、平台信息 |

---

## 五、核心业务流程

### 5.1 认证流程

```
请求 → auth_required 装饰器
  ├─ web_password 为空 → 放行
  ├─ session['authenticated'] = True → 放行
  ├─ API 路由 → 返回 401 JSON
  └─ 页面路由 → 重定向 /login

POST /login:
  ├─ 比对 web_username / web_password
  ├─ 成功 → session['authenticated'] = True → 重定向 /dashboard
  └─ 失败 → 重新渲染 login.html + 错误提示
```

### 5.2 订阅刷新流程

```
POST /api/subscriptions/<id>/refresh
  → subscription_service.refresh(sub_id):
    1. db 获取订阅记录
    2. HTTP GET 订阅 URL (Clash UA, 禁用 SSL 验证)
    3. 解析 Subscription-Userinfo 响应头 (流量信息)
    4. Base64 解码内容
    5. 检测格式:
       a. Clash YAML → yaml.safe_load → 遍历 proxies
       b. 标准格式 → 逐行解码 vmess:// 和 ss://
    6. 每个节点自动分配 bin_type:
       - SS + obfs 插件 → sslocal
       - Hysteria2 / TUIC → sing-box
       - 其他 → xray
    7. 应用 filter_keywords / exclude_keywords 过滤 (OR 逻辑)
    8. db 清空旧节点 → 批量写入新节点 → 更新 updated_at
```

### 5.3 服务启动流程

```
POST /api/services/<id>/start
  → service_manager.start(service_id):
    1. db 获取 service + inbound + outbound
    2. 检查是否已在运行 → 拒绝
    3. 验证入站端口可用 (bind check)
    4. 解析出站节点:
       - single → config_json.node_id
       - auto → 节点池中 priority 最小的节点
    5. 分配空闲 SOCKS5 端口 (50000-60000 范围随机)
    6. 生成 Xray 入站配置 (监听用户端口 → SOCKS5)
    7. 生成出站二进制配置 (SOCKS5 → 代理节点)
    8. 写入两个 JSON 配置文件到 config/<service_name>/
    9. 启动 Xray 入站进程 → 写 PID 文件
   10. 启动出站二进制进程 → 写 PID 文件
   11. 如出站启动失败 → 停止 xray 回滚
   12. 更新 DB 状态为 'running'
```

### 5.4 服务停止流程

```
POST /api/services/<id>/stop
  → service_manager.stop(service_id):
    1. 遍历 BIN_REGISTRY 中所有 bin_type
    2. 对每个运行中的进程:
       a. 读取 PID 文件
       b. 发送 SIGTERM
       c. 等待最多 3 秒 (10 × 0.3s)
       d. 若未退出 → 发送 SIGKILL
       e. 清理 PID 文件
    3. 更新 DB 状态为 'stopped'
```

### 5.5 节点健康检测流程

```
POST /api/nodes/check {node_ids?: [...], check_type: 'tcp'|'url'|'both'}
  → checker.check(nodes, check_type):
    全局锁 (同时只允许一个检测任务)
    对每个节点:
      1. TCP Ping:
         subprocess → bash scripts/test.sh tcp_ping <addr> <port> <timeout> <tag>
         解析 JSON 返回 {success, latency_ms}
      2. URL Test (仅在 TCP 成功或单独执行时):
         a. 生成临时配置文件
         b. subprocess → bash scripts/test.sh url_test (JSON via stdin)
           脚本内部: 启动代理 → 等待端口 → curl SOCKS5 → 清理进程
         c. 解析 JSON 返回 {success, http_code, latency_ms}
         d. 清理临时配置文件
      3. 更新 DB latencies
    多节点时返回 task_id (后台线程执行)，可通过 GET /check/<task_id>/status 轮询进度
```

### 5.6 二进制升级流程

```
GET /api/upgrade/check/<bin_name>
  → upgrade_service.check(bin_name):
    1. 确认平台支持
    2. GitHub API: repos/{repo}/releases/latest
    3. 按平台模式匹配 assets
    4. 对比当前版本 vs 远程版本
    5. 检查插件状态

POST /api/upgrade/download/<bin_name>
  → upgrade_service.download(bin_name):
    1. 检查更新
    2. 若已是最新 → 检查并下载缺失插件
    3. 下载匹配平台的 asset
    4. 按扩展名解压:
       .zip → zipfile
       .tar.gz / .tar.xz → tarfile
    5. 提取二进制到 bin/，chmod 755
    6. 处理插件 (obfs-local):
       a. 检查 bin/ 目录 → 已存在则跳过
       b. 检查系统 PATH (shutil.which) → 找到则复制到 bin/
       c. 均未找到 → 记录日志提示 apt install simple-obfs
```

---

## 六、关键数据结构

### 6.1 二进制注册表

```python
BIN_REGISTRY = {
    'xray': {
        'exe': 'xray',
        'version_args': ['version'],
        'run_args': ['run', '-config', '{config}'],
    },
    'sslocal': {
        'exe': 'sslocal',
        'version_args': ['--version'],
        'run_args': ['-c', '{config}'],
    },
    'sing-box': {
        'exe': 'sing-box',
        'version_args': ['version'],
        'run_args': ['run', '-c', '{config}'],
    },
}
```

### 6.2 GitHub 仓库配置

```python
BIN_REPOS = {
    'xray': {
        'repo': 'XTLS/Xray-core',
        'exe_names': ['xray'],
        'asset_patterns': {'linux-64': ['linux-64', 'linux-x64']},
    },
    'sslocal': {
        'repo': 'shadowsocks/shadowsocks-rust',
        'exe_names': ['sslocal'],
        'asset_patterns': {'linux-64': ['x86_64-unknown-linux']},
        'plugins': [{
            'name': 'obfs-local',
            'repo': 'shadowsocks/simple-obfs',
            'exe_names': ['obfs-local'],
            'asset_patterns': {'linux-64': ['obfs-local']},
        }],
    },
    'sing-box': {
        'repo': 'SagerNet/sing-box',
        'exe_names': ['sing-box'],
        'asset_patterns': {'linux-64': ['linux-amd64', 'linux-x64']},
    },
}
```

### 6.3 协议到 bin_type 的映射

```python
PROTOCOL_BIN_MAP = {
    # SS + obfs 插件 → sslocal; SS 无插件 → xray
    # 在解析时根据 plugin 字段动态判定
    'vmess':     'xray',
    'vless':     'xray',
    'trojan':    'xray',
    'ssr':       'xray',
    'anytls':    'xray',
    'hysteria':  'sing-box',
    'hysteria2': 'sing-box',
    'tuic':      'sing-box',
}
```

### 6.4 有效入站协议

```python
VALID_INBOUND_PROTOCOLS = ('http', 'socks', 'ss', 'vmess')
```

---

## 七、订阅解析规范

> 订阅解析是与机场/服务商对接的核心模块，已通过大量真实订阅链接调试验证。
> 重写时必须严格遵循以下规则，避免解析失败、bin_type 分配错误、插件不生效。

### 7.1 获取订阅内容

```
GET <subscription_url>
  Headers:
    User-Agent: ClashForAndroid/2.5.12   ← 必须，否则拿不到流量信息头
    Accept: */*
  SSL: 禁用证书验证（机场常用自签证书）
  Timeout: 30s
```

响应处理：
1. 解析 `Subscription-Userinfo` 头，格式 `upload=0; download=123; total=456; expire=789`，提取四个整数字段
2. 对 body 尝试 Base64 解码（补齐 `=` padding 到 4 的倍数），解码后含 `vmess://` 或 `ss://` 则使用解码内容

### 7.2 格式检测

```
content 以 "mixed-port:" 开头 或 含 "proxies:" → Clash YAML 格式
否则 → 标准格式（逐行 vmess:// / ss:// 链接）
```

### 7.3 标准格式：vmess://

```
vmess://<base64_json>

1. 去掉前缀 "vmess://"
2. 补齐 base64 padding
3. Base64 解码 → JSON: {ps, add, port, id, aid, net, type, host, path, tls}
4. 映射:
   name = ps
   addr = add
   port = int(port)
   config = {id, aid, net, type, host, path, tls}
   bin_type = 'xray' (固定)
```

### 7.4 标准格式：ss://

支持两种格式：
```
SIP002:  ss://base64(method:password)@server:port#name
Legacy:  ss://base64(method:password@server:port)#name
```

解码流程：
```
1. 去掉 "ss://" 前缀
2. 按 # 分割 → fragment (URL decode → name)
3. 按 ? 分割 → query params, 提取 plugin= (URL decode)
4. 按 @ 分割:
   - 前: base64 decode → method:password
   - 后: 去掉末尾 /, 按 : 分割最后一段 → address:port
5. 无 @ 的 legacy 格式: 整体 base64 解码后再解析
```

bin_type 规则：
```
if plugin 含 "obfs":
    config.plugin = 'obfs-local'
    config.plugin_opts = plugin 中 ; 之后的部分
    bin_type = 'sslocal'
else:
    bin_type = 'xray'
```

注意：v2ray-plugin 等非 obfs 插件忽略不处理。

### 7.5 Clash YAML 格式

YAML 解析策略：
```
1. yaml.safe_load(content) 整体解析
2. 失败 → 提取 "proxies:" 到下一个顶层 key 之间再解析
   (收集非缩进非列表行之前的所有缩进行/列表行)
```

各类型的字段映射（只列与标准格式有差异的）：

**SS** (`type: ss`):
```
cipher → method      plugin → 仅 "obfs" 有效
plugin-opts.mode → obfs=     plugin-opts.host → obfs-host=
有 obfs → sslocal, 无 → xray
```

**SSR** (`type: ssr`): cipher/password/obfs/protocol/obfs-param/protocol-param → xray

**VMess** (`type: vmess`):
```
uuid→id   alterId→aid(int)   cipher→security
network/ws-opts/h2-opts/grpc-opts 按网络类型提取
tls/sni/skip-cert-verify 逐字段映射
→ xray
```

**VLESS** (`type: vless`):
```
uuid→id   flow/encryption 映射
reality-opts: public-key→reality_public_key, short-id→reality_short_id
ws-opts/grpc-opts 同 vmess (无 h2)
→ xray
```

**Trojan** (`type: trojan`):
```
password/sni/alpn/skip-cert-verify 映射
ws-opts/grpc-opts 同 vmess
→ xray
```

**Hysteria/Hysteria2** (`type: hysteria/hysteria2/hy2`):
```
password(或auth)→password   sni/skip-cert-verify 映射
up-mbps→up_mbps   down-mbps→down_mbps
obfs/obfs-password (仅 hy2)
→ sing-box
```

**TUIC** (`type: tuic`):
```
uuid/password/sni/skip-cert-verify/alpn 映射
congestion-control('cubic'默认)  udp-relay-mode('native'默认)
→ sing-box
```

**anyTLS** (`type: anytls`): password/sni/skip-cert-verify → xray

### 7.6 bin_type 自动分配总表

| 协议 | bin_type | 备注 |
|------|----------|------|
| vmess / vless / trojan / ssr / anytls | `xray` | — |
| ss (无插件) | `xray` | Xray 支持 SS |
| ss (有 obfs) | `sslocal` | Xray 不支持 obfs 插件 |
| hysteria / hysteria2 / hy2 | `sing-box` | — |
| tuic | `sing-box` | — |

### 7.7 关键字过滤

```
filter_keywords:  按 \n 或 , 分割, 节点名含任一 → 保留 (OR)
exclude_keywords: 按 \n 或 , 分割, 节点名含任一 → 排除 (OR)
空 → 不过滤
```

### 7.8 前端节点编辑用映射

```python
VALID_BIN_TYPES = {
    'vmess':     ['xray'],
    'vless':     ['xray'],
    'trojan':    ['xray'],
    'ss':        ['xray', 'sslocal'],   # 选 xray 时隐藏插件字段
    'ssr':       ['xray'],
    'hysteria2': ['sing-box'],
    'tuic':      ['sing-box'],
}
```

---

## 八、重要设计约束

### 8.1 main.py / routes 的准则
- **每个路由处理函数不超过 10 行**
- 只做：参数提取 → 调用 service → 格式化返回
- 不做：数据库操作、业务判断、配置生成、进程管理
- 认证装饰器 `@auth_required` 单独定义在 `routes/__init__.py`

### 8.2 仅 Ubuntu 22.04+ 支持
- 平台检测仅返回 `linux-64`
- 进程管理使用 POSIX 信号 (SIGTERM/SIGKILL)
- 二进制名称无平台后缀（无 `.exe`）
- 依赖命令: `bash`, `python3`, `curl`, `setsid`, `pgrep`（Ubuntu 预装）

### 8.3 进程管理
- PID 文件格式: `data/{service_name}_{bin_name}.pid`
- 启动: subprocess.Popen, stdout/stderr → DEVNULL
- 停止: SIGTERM → 等 3s → SIGKILL → 清理 PID 文件
- 版本: subprocess.run(bin_path + version_args, timeout=5)
- 运行检查: os.kill(pid, 0)
- 运行时长: os.stat(f'/proc/{pid}').st_ctime

### 8.4 健康检测脚本
- 保持 `scripts/test.sh` bash 脚本
- 两个子命令: `tcp_ping` / `url_test`
- JSON 输出到 stdout
- 三层孤儿进程清理: PGID kill → tag pgrep → config-filename pgrep
- 依赖: bash, python3, curl, setsid, pgrep

### 8.5 二进制升级
- 下载超时: 120 秒
- 解压后必须 `chmod 0o755`
- 支持格式: `.zip`, `.tar.gz`, `.tar.xz`
- 插件 simple-obfs: 检查 bin/ → 检查系统 PATH → 均无则日志提示 `apt install simple-obfs`

### 8.6 配置生成
- Xray 入站: 监听用户端口，转发到本地 SOCKS5
- 出站二进制: 接收 SOCKS5，转发到远程代理节点
- SOCKS5 端口: 50000-60000 范围随机分配
- 配置文件: `config/<service_name>/xray.json` + `config/<service_name>/<bin_type>.json`

### 8.7 日志系统
- `app/logger.py`: WebLogger 类
- 捕获 stdout/stderr 到内存 deque (最多 500 条)
- API: 返回 since 索引之后的新日志
- 日志级别: info / ok / warn / error
- 抑制 werkzeug 的请求日志（避免轮询日志循环）

---

## 九、setup.sh 部署脚本

```bash
#!/bin/bash
set -e

echo "=== ProxyHub Setup ==="

# 1. 系统依赖
echo "[1/3] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv curl simple-obfs

# 2. Python 环境
echo "[2/3] Setting up Python environment..."
python3 -m venv venv
./venv/bin/pip install -q flask pyyaml

# 3. 目录结构
echo "[3/3] Creating directories..."
mkdir -p bin config data

echo ""
echo "Setup complete."
echo "Run: ./venv/bin/python run.py"
echo "Then open http://<server-ip>:8080"
```

---

## 十、待实现功能（本次预留接口）

### 9.1 节点自动故障转移
- **状态**: 预留，不实现
- **接口预留位置**: `app/services/service_manager.py` 中预留 `_check_and_failover()` 方法
- **数据已具备**: `outbound_nodes` 表的 `priority` 字段
- **设置已具备**: `check_interval_normal`, `check_interval_failover`

---

## 十一、实现顺序建议

按以下顺序开发，每个阶段可独立测试：

### Phase 1: 基础设施
1. `app/settings.py` — 配置常量
2. `app/utils/` — 工具函数
3. `app/logger.py` — 日志系统
4. `app/models/database.py` — 数据库连接 + 初始化 + 迁移
5. `app/models/*.py` — 各表 CRUD

### Phase 2: 核心服务
6. `app/services/auth_service.py` — 认证
7. `app/engine/*.py` — 配置生成
8. `app/process/manager.py` — 进程管理
9. `app/services/config_service.py` — 配置服务
10. `app/services/service_manager.py` — 服务启动/停止
11. `app/services/subscription_service.py` — 订阅解析
12. `app/services/node_service.py` — 节点管理 + 验证
13. `app/services/outbound_service.py` — 出站管理
14. `app/services/upgrade_service.py` — 升级服务
15. `app/checker/*.py` — 健康检测

### Phase 3: 路由 + 模板
16. `app/routes/__init__.py` — 应用工厂 + auth 装饰器
17. `app/routes/*.py` — 所有路由
18. `templates/` — 复用现有模板，调整 API 路径
19. `run.py` — 入口

### Phase 4: 收尾
20. `setup.sh` — 部署脚本
21. `requirements.txt` — 依赖声明
22. 端到端测试

---

## 十二、前端模板规范

> 所有页面使用纯 HTML/CSS/JS，无任何前端框架。Jinja2 模板引擎渲染。

### 11.1 全局设计系统

#### 色彩
```
背景:   #fff (卡片/模态框), #fafafa (页面/输入框)
边框:   #e0e0e0
文字:   #333 (主), #888 (次), #bbb (禁用)
强调:   #1976d2 (模块名蓝)
状态:   #4caf50 (成功绿), #e53935 (错误红), #ffa726 (警告橙)
```

#### 字体
```
字体栈: 'Consolas', 'Monaco', 'Courier New', monospace
基准:   13px
小字:   11-12px (标签、表头、meta)
标题:   14px bold (卡片标题、模态框标题)
大数:   16px bold (统计数值)
```

#### 间距系统
```
4px   — 按钮组 gap, 标签内边距, 关键字行 gap
6px   — 状态点尺寸, 节点行 padding
8px   — 卡片间 gap, 节点列 gap
12px  — section body padding, stat item padding, card margin-bottom
16px  — sub-card margin-bottom, radio-group gap
20px  — modal padding
```

#### 按钮体系
| 类名 | 用途 | 样式 |
|------|------|------|
| `.btn` | 默认 | 白底 `#ccc` 边框, 28px 高, 4-14px 水平 padding |
| `.btn-sm` | 紧凑 | 2px 8px padding, 11px 字 |
| `.btn-primary` | 主操作 | `#333` 深底白字, hover `#555` |
| `.btn-danger` | 危险操作 | 红色边框/文字 `#e53935`, hover 粉色底 `#fce4ec` |
| `.btn-ok` | 成功/确认 | 绿色边框/文字 `#4caf50`, hover 绿色底 `#e8f5e9` |
| `.btn-ghost` | 无边框 | 无边, 灰色 `#888` |
| `:disabled` | 禁用 | `#bbb` 文字, `#e0e0e0` 边框, `cursor:not-allowed` |

#### 表单元素
- `.input`: 28px 高, `#fafafa` 底, `#e0e0e0` 边框, focus 时 outline 为 `#999`
- `textarea.input`: 最小 80px 高, 行高 1.6
- `.field`: `margin: 10px 0`, 内含 label + input
- `.field-row`: flex 行, 12px gap, 子元素 flex:1
- `select.input`: 同 input 样式
- `.radio-group`: flex 行, 16px gap, 子元素 12px 字 + cursor pointer

#### 标签 Tag
- `.tag`: 行内块, `1px 6px` padding, `#e0e0e0` 边框, 11px 字, 协议/类型标识

#### 状态点
- `.status-dot`: 6px 圆形, 行内块
- `.ok` 绿 `#4caf50`, `.error` 红 `#e53935`, `.idle` 灰 `#bbb`

#### 卡片 Section
- `.section`: 带边框卡片, 16px margin-bottom
- `.section-title`: bold 12px 灰色标题行, 12px padding, `#fafafa` 底
- `.section-body`: 12px padding

### 11.2 base.html — 应用外壳

所有页面（除 login.html）继承此模板。

#### 布局结构 (flex 全屏, 固定高度)
```
┌─────────────────────────────────────────────┐
│ Navbar (44px)    [App名]         [操作按钮] │
├────────┬────────────────────────────────────┤
│ Sidebar│  Content (flex:1, overflow-y:auto) │
│ 200px  │                                    │
│ 导航   │   {% block content %}              │
│        │                                    │
├────────┴────────────────────────────────────┤
│ Log Panel (底部, 可折叠, 160px max)         │
│ ─────────────────────────────────────────── │
│ ▲ Logs                            [N lines] │ ← 点击切换 显示/隐藏
│ 09:53:49 [system] webui started             │
│ 09:54:10 [xray]   checking update...        │
├─────────────────────────────────────────────┤
│ Status Bar (24px)  ●xray ●ss ●sing-box  N nodes │
└─────────────────────────────────────────────┘
```

#### Sidebar 导航
| 链接 | URL | page 变量 |
|------|-----|-----------|
| dashboard | `/` | `dashboard` |
| inbounds | `/inbounds` | `inbounds` |
| outbounds | `/outbounds` | `outbounds` |
| subscriptions | `/subscriptions` | `subscriptions` |
| nodes | `/nodes` | `nodes` |
| settings | `/settings` | `settings` |

当前页使用 `.list-item.active` (左侧强调边框)。

#### Jinja2 Block 体系
| Block | 用途 |
|-------|------|
| `{% block title %}` | 页面标题, 默认 `{{ app_name }}` |
| `{% block navbar_actions %}` | 导航栏右侧操作按钮 |
| `{% block extra_css %}` | 页面专用 CSS, 包裹在 `<style>` 内 |
| `{% block content %}` | 主内容区 |
| `{% block statusbar_right %}` | 状态栏右侧扩展信息 |
| `{% block modals %}` | 模态框 HTML, 放在 `</body>` 前 |
| `{% block extra_js %}` | 页面专用 JS, 包裹在 `<script>` 内 |

#### 全局 JavaScript
base.html 提供以下全局函数，子页面直接使用：

| 函数 | 说明 |
|------|------|
| `toggleLog()` | 折叠/展开日志面板, 翻转箭头方向 |
| `addLog(level, msg)` | 向日志区追加一行, 自动滚动到底部 |
| `fetchLogs()` | 轮询 GET `/api/logs?since=N`, 追加新日志, 每 2 秒 |
| `escapeHtml(text)` | HTML 转义 (借 DOM textContent) |
| `checkBinsStatus()` | GET `/api/bins/status`, 更新状态栏进程圆点, 每 10 秒 |

日志行格式: `HH:MM:SS [module] message`, 按级别着色 (info 默认, ok 绿, warn 橙, error 红)。

### 11.3 login.html — 登录页

**不继承 base.html**, 独立 HTML 文档。

```
        ┌─────────────────┐
        │   ProxyHub      │
        │                 │
        │ [Username     ] │
        │ [Password     ] │
        │                 │
        │ [   Login    ]  │
        │                 │
        │ 错误提示(红色)   │
        └─────────────────┘
```

- 300px 宽白色卡片, 居中, 4px 圆角, 30px padding
- 传统 `<form method="POST">`, 非 AJAX
- 如有错误, 服务器渲染 `{{ error }}` 红色文字
- 输入框 `#fafafa` 底, focus 边框变 `#999`
- 按钮 `#333` 深底白字, hover `#555`, 全宽

### 11.4 dashboard.html — 仪表盘

#### 内容分区
1. **统计栏** (5 列 flex): 节点数 / 订阅数 / xray 状态 / sslocal 状态 / sing-box 状态
2. **服务列表**: 卡片式, 每 10 秒自动刷新

#### 统计卡片数据源
| 指标 | 来源 |
|------|------|
| 节点数 | `GET /api/nodes/grouped` → 统计所有 group 的 nodes |
| 订阅数 | 同上, 统计 `sub.id !== 0` 的 group 数 |
| 引擎状态 | `GET /api/bins/status` |

#### 服务卡片

```
┌──────────────────────────────────────────────────┐
│ ● service-name  :8080 (http)   [☐auto][▶][■][✎][✕]│
│ ┌──────────────────┐  →  ┌──────────────────────┐ │
│ │ HTTP :8080        │     │ outbound-name       │ │
│ │ user: admin       │     │ 3 nodes in pool     │ │
│ └──────────────────┘     └──────────────────────┘ │
└──────────────────────────────────────────────────┘
```

- 头部: 状态点 + 服务名 + 端口/协议 + 操作按钮
- 操作: auto-start 复选框, start, stop, restart, edit, delete
- 体部: 入站信息 → 箭头 → 出站信息

#### 模态框
1. **serviceModal**: name + inbound 下拉 + outbound 下拉, 支持 create/edit 双模式
2. **deleteModal**: 确认消息 + 确认按钮
3. **messageModal**: 通用错误/通知提示

#### AJAX 调用
- `GET /api/nodes/grouped` + `GET /api/bins/status` + `GET /api/services` — 每 10 秒
- `POST /api/services/<id>/start|stop|restart` — 服务控制
- `PUT /api/services/<id>` — 切换 auto_start
- `DELETE /api/services/<id>` — 删除

### 11.5 nodes.html — 节点管理

#### 内容: 按订阅分组的折叠列表

```
┌──────────────────────────────────────────────────┐
│ ▼ subscription-name  · N nodes      [check all] │ ← 折叠头
├──────────────────────────────────────────────────┤
│ name │proto│bin │address:port │ tcp │ url │ act  │ ← 列头
│ node1│vmess│xray│1.2.3.4:443 │ 45ms│200ms│◎✎✕  │
│ node2│ss   │ssloc│5.6.7.8:8388│150ms│  -  │◎✎✕  │
└──────────────────────────────────────────────────┘
│ ▶ subscription2-name  · N nodes     [check all] │ ← 折叠闭
└──────────────────────────────────────────────────┘
│ Custom Nodes (无订阅)                           │
└──────────────────────────────────────────────────┘
```

#### 延迟着色
| TCP 延迟 | URL 延迟 | 类名 |
|----------|----------|------|
| null | null | `lat-pending` 灰 |
| < 0 (失败) | < 0 (失败) | `lat-bad` 红 |
| ≤ 150ms | ≤ 1000ms | `lat-ok` 绿 |
| ≤ 300ms | ≤ 2000ms | `lat-warn` 橙 |
| > 300ms | > 2000ms | `lat-bad` 红 |

#### 检测流程
- 单节点: POST `/api/nodes/check` → 同步等结果 → 更新显示
- 批量: POST `/api/nodes/check` → 获得 task_id → 每 1.5s 轮询 `/api/nodes/check/<taskId>/status` → 逐个更新延迟 → 直到 running=false

#### 节点模态框 (协议自适应)
- **URL 导入区**: 粘贴 vmess:// vless:// ss:// trojan:// hy2:// 链接, 点击解析
- **基础字段**: name, protocol 下拉, bin_type 下拉(根据 protocol 过滤), address, port
- **协议字段**: 根据 protocol 动态显示/隐藏:
  - VMess: uuid, alterId, security
  - VLESS: uuid, flow, encryption
  - SS: method, password, plugin, plugin_mode, plugin_host
  - Trojan: password, alpn
  - Hysteria2: password, obfs, obfs_password, up_mbps, down_mbps
- **传输层** (vmess/vless/trojan): network (tcp/ws/h2/grpc) → 动态子字段
- **TLS**: tls 开关, sni, alpn, allowInsecure, fingerprint
- **提交**: 拼装所有字段为 config_json JSON 字符串

#### 协议→bin_type 映射
```javascript
VALID_BIN_TYPES = {
    vmess:     ['xray'],
    vless:     ['xray'],
    trojan:    ['xray'],
    ss:        ['xray', 'sslocal'],   // 有 obfs 插件 → sslocal; 无 → xray
    hysteria2: ['sing-box'],
    tuic:      ['sing-box']
};
```

### 11.6 outbounds.html — 出站管理

#### 内容: 卡片式 (每张一个出站)

```
┌──────────────────────────────────────────────────┐
│ outbound-name  [single] node-name (vmess 1.2.3.4:443) [✎][✕]│
│ ┌──────────────────────────────────────────────┐ │
│ │ Fixed proxy through node-name               │ │
│ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ auto-outbound  [auto] 3 nodes · check: 240s  [✎][✕]│
│ ┌──────────────────────────────────────────────┐ │
│ │ # │proto│name    │addr:port   │latency│act  │ │
│ │ 1 │vmess│node-a  │1.2.3.4:443│ 45ms │▲▼ ✕ │ │
│ │ 2 │ss   │node-b  │5.6.7.8:888│150ms │▲▼ ✕ │ │
│ │ [+ add node]                                 │ │
│ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

#### 节点池操作
- **添加**: 弹出选择器, 已入池的节点灰显不可选
- **移除**: 点击 ✕, 直接 DELETE
- **排序**: 点击 ▲ 上移, ▼ 下移, 交换后 POST reorder
- **优先级**: 第一行自动标记为 `pool-cur` 绿色

### 11.7 subscriptions.html — 订阅管理

#### 内容: 订阅卡片 + 关键字编辑

```
┌──────────────────────────────────────────────────┐
│ subscription-name · N nodes  [updated: ...] [◎][✎][✕]│
│ ──────────────────────────────────────────────── │
│ Traffic: 1.2 GB / 5.0 GB — 3.8 GB remaining     │
│ Expires: 2026-07-15 (23 days)                   │
│ ──────────────────────────────────────────────── │
│ filter  │ click to set filter keywords           │ ← 点击打开编辑
│ exclude │ click to set exclude keywords          │
│ N nodes available                                │
└──────────────────────────────────────────────────┘
```

#### 流量显示
- `formatBytes(bytes)` 工具函数: B → KB → MB → GB → TB, 1 位小数
- 剩余流量用 (total - used) 计算
- 到期倒计时: `expire_at` 时间戳距离现在的天数

#### 关键字编辑
- `filter_keywords`: OR 匹配, 包含任一关键字的节点保留
- `exclude_keywords`: OR 匹配, 包含任一关键字的节点排除
- 编辑模态框: textarea, 每行一个关键字
- 提交: PUT `/api/subscriptions/<id>` 只更新 {filter_keywords} 或 {exclude_keywords}

### 11.8 inbounds.html — 入站管理

#### 内容: 表格式

```
┌──────────────────────────────────────────────────┐
│ name │protocol│listen      │params      │actions │
│ my-http│[http]│0.0.0.0:8080│user: admin │[✎][✕] │
│ my-ss  │[ss]  │0.0.0.0:8388│aes-256-gcm │[✎][✕] │
│ my-vmess│[vmess]│0.0.0.0:443│e4f8... ws:/ws│[✎][✕]│
└──────────────────────────────────────────────────┘
```

#### 模态框 (协议自适应)
| 协议 | 参数字段 |
|------|---------|
| HTTP/SOCKS | username, password |
| Shadowsocks | method(下拉), password |
| VMess | uuid, alterId, transport(tcp/ws/h2/grpc) + 动态子字段 |

### 11.9 settings.html — 设置页

#### 内容: 6 个 Section

1. **Binaries**: 每个引擎一行, 显示版本 + 检查更新按钮 + 展开的下载区
2. **Binary paths**: 4 个文本输入 (xray/sslocal/sing-box 路径 + config 目录)
3. **Node check**: 检测间隔/超时设置 + test_url + auto_failover 开关
4. **Web UI**: port, username, password, confirm password
5. **System info**: 数据库大小 (只读), 平台信息 (只读)
6. **Danger zone**: 3 个危险按钮 (清空节点/重置设置/清空数据库)

#### 交互
- **保存**: 计算变更 diff (新旧值对比), 弹窗确认, POST `/api/settings`
- **危险操作**: 弹出输入框, 必须输入对应动作名才可确认

### 11.10 通用组件模式

#### 模态框 (CSS + JS)
```css
.modal-overlay         /* fix 全屏, #0003 底, display:none, flex 居中 */
.modal-overlay.show    /* display:flex */
.modal                 /* 白底, 380px, 4px 圆角, 20px padding */
.modal-title           /* bold 14px */
.modal-actions         /* flex-end, 16px gap, 8px gap */
```

JS 模式:
```javascript
// 显示: 加到 overlay 的 classList
document.getElementById('xxxModal').classList.add('show');
// 隐藏: 移除 class
document.getElementById('xxxModal').classList.remove('show');
```

#### 删除确认 (通用模式)
每个实体（节点、入站、出站、服务、订阅）使用相同的删除确认模式：
1. 设置 `deleteMessage` 文字内容
2. `deleteConfirmBtn.onclick` 绑定到发送 DELETE 请求
3. 显示 `deleteModal`

#### 折叠 (Accordion)
- `.collapse-header`: 可点击, 切换 `.collapse-body.show`
- 箭头: ▼ 展开 / ▶ 闭合

#### 空状态
- `.empty-state`: 居中, 40px padding, `#888` 灰色, 斜体

### 11.11 前端实现注意事项

1. **escapeHtml() 去重**: 当前每个页面都重复定义。应在 base.html 定义一次, 子页面继承使用。
2. **无前端框架**: 纯 vanilla JS + DOM 操作 + fetch API。不要引入 React/Vue/jQuery。
3. **轮询策略**: 日志 2s, 状态栏 10s, 仪表盘 10s, 批量检测 1.5s。
4. **config_json**: 所有节点/入站的协议参数都序列化为 JSON 字符串存储在单个字段中, 前端负责解析和拼装。
5. **密码脱敏**: 设置 API 返回 `******`, 前端提交时如果未修改则传 `******` 表示不更新。
6. **所有用户输入都经 escapeHtml()**: 节点名、订阅名、服务名等用户数据渲染到 HTML 前必须转义。
7. **日志集成**: 每个用户操作调用 `addLog()` 写入底部日志面板 (级别: ok/warn/error)。

---

## 十三、Flask 应用工厂

```python
# app/__init__.py
from flask import Flask

def create_app():
    app = Flask(__name__, template_folder='../templates')
    app.secret_key = os.urandom(24)

    from .routes import register_blueprints
    register_blueprints(app)

    # 启动 auto-start 守护线程
    from .services.service_manager import start_auto_start_daemon
    start_auto_start_daemon(app)

    return app
```

```python
# run.py
from app import create_app
from app.settings import get_setting

if __name__ == '__main__':
    app = create_app()
    port = int(get_setting('web_port') or 8080)
    app.run(debug=True, host='0.0.0.0', port=port)
```

---

## 十四、引擎配置 JSON 规范

> 本章定义三个代理引擎的完整 JSON 配置结构。重写时必须严格按照这些结构生成配置，
> 否则代理进程将无法识别或行为异常。

### 14.1 Xray 配置

Xray 使用嵌套 JSON 结构，顶层包含 `inbounds` 和 `outbounds` 两个数组。

#### 通用出站模板

所有 Xray 出站配置共享以下骨架：

```json
{
    "inbounds": [{
        "protocol": "socks",
        "port": <local_port>,
        "listen": "127.0.0.1"
    }],
    "outbounds": [{
        "protocol": "<protocol>",
        "settings": { ... },
        "streamSettings": { ... }
    }]
}
```

#### 各协议 settings 结构

**VMess:**
```json
{
    "protocol": "vmess",
    "settings": {
        "vnext": [{
            "address": "<address>",
            "port": <port>,
            "users": [{
                "id": "<uuid>",
                "alterId": <int, default 0>,
                "security": "<auto|aes-128-gcm|chacha20-poly1305|none, default 'auto'>"
            }]
        }]
    }
}
```

**VLESS:**
```json
{
    "protocol": "vless",
    "settings": {
        "vnext": [{
            "address": "<address>",
            "port": <port>,
            "users": [{
                "id": "<uuid>",
                "encryption": "<'none'>",
                "flow": "<optional, only when set>"
            }]
        }]
    }
}
```

**Trojan:**
```json
{
    "protocol": "trojan",
    "settings": {
        "servers": [{
            "address": "<address>",
            "port": <port>,
            "password": "<password>"
        }]
    }
}
```

**Shadowsocks (Xray 使用 `shadowsocks` 协议名):**
```json
{
    "protocol": "shadowsocks",
    "settings": {
        "servers": [{
            "address": "<address>",
            "port": <port>,
            "method": "<aes-256-gcm, default>",
            "password": "<password>"
        }]
    }
}
```

#### streamSettings 构建规则

```python
def build_stream_settings(cfg):
    stream = {"network": cfg.get('network', 'tcp'),
              "security": "tls" if cfg.get('tls') else "none"}

    if cfg['tls']:
        tls = {}
        if cfg.get('sni'):       tls['serverName'] = cfg['sni']
        if cfg.get('allowInsecure'): tls['allowInsecure'] = True
        if cfg.get('fingerprint'):   tls['fingerprint'] = cfg['fingerprint']
        if cfg.get('alpn'):
            alpn = cfg['alpn']
            tls['alpn'] = alpn.split(',') if isinstance(alpn, str) else alpn
        if tls: stream['tlsSettings'] = tls

    if network == 'ws':
        ws = {}
        if cfg.get('ws_host'): ws['headers'] = {'Host': cfg['ws_host']}
        if cfg.get('ws_path'): ws['path']     = cfg['ws_path']
        if ws: stream['wsSettings'] = ws

    elif network in ('h2', 'http'):
        h2 = {}
        if cfg.get('h2_host'):
            host = cfg['h2_host']
            h2['host'] = [host] if isinstance(host, str) else host
        if cfg.get('h2_path'): h2['path'] = cfg['h2_path']
        if h2: stream['httpSettings'] = h2

    elif network == 'grpc':
        grpc = {}
        if cfg.get('grpc_service_name'): grpc['serviceName'] = cfg['grpc_service_name']
        if grpc: stream['grpcSettings'] = grpc

    return stream
```

**注意**: `cfg` 是节点表中 `config_json` 字段解析后的 dict，字段名使用 snake_case（如 `ws_host`、`grpc_service_name`），映射到 Xray JSON 时转为 camelCase（如 `wsSettings`、`serviceName`）。

#### Xray 入站配置（service 使用）

Xray 入站是双进程管道的第一段：监听用户端口 → 转发到本地 SOCKS5。

```json
{
    "inbounds": [<inbound_config>],
    "outbounds": [{
        "protocol": "socks",
        "settings": {
            "servers": [{
                "address": "127.0.0.1",
                "port": <socks_port>
            }]
        }
    }]
}
```

`inbound_config` 按协议：

**HTTP / SOCKS:**
```json
{
    "protocol": "http",     // 或 "socks"
    "port": <port>,
    "listen": "0.0.0.0",
    "settings": {           // 有认证时才有
        "accounts": [{"user": "...", "pass": "..."}]
    }
}
```

**Shadowsocks (Xray 协议名为 `shadowsocks`):**
```json
{
    "protocol": "shadowsocks",
    "port": <port>,
    "listen": "0.0.0.0",
    "settings": {
        "method": "<aes-256-gcm>",
        "password": "<password>"
    }
}
```

**VMess:**
```json
{
    "protocol": "vmess",
    "port": <port>,
    "listen": "0.0.0.0",
    "settings": {
        "clients": [{"id": "<uuid>", "alterId": <int>}]
    },
    "streamSettings": {      // 仅当 config_json 中有 network 字段
        "network": "<tcp|ws|h2|grpc>",
        "wsSettings": {"path": "<path>"}  // ws 时
    }
}
```

**关键映射**: 入站协议 `ss` → Xray 协议名 `shadowsocks`。

### 14.2 sslocal 配置

**完全不同**: sslocal 使用扁平 JSON，无 inbounds/outbounds 包装：

```json
{
    "server":        "<address>",
    "server_port":   <port>,
    "password":      "<password>",
    "method":        "<aes-256-gcm, default>",
    "local_address": "127.0.0.1",
    "local_port":    <local_port>,
    "plugin":        "obfs-local",      // 仅当有 obfs 插件
    "plugin_opts":   "obfs=http;obfs-host=..."  // 仅当有插件参数
}
```

- `plugin` 和 `plugin_opts` 字段仅在 `config_json.plugin` 存在时添加
- 不支持 obfs 以外插件
- 协议必须为 `ss`，否则抛出 `ValueError`

### 14.3 sing-box 配置

sing-box 使用 `type` 而非 `protocol`，TLS 字段命名不同于 Xray。

```json
{
    "inbounds": [{
        "type": "socks",
        "listen": "127.0.0.1",
        "listen_port": <local_port>    // 注意: 是 listen_port 不是 port
    }],
    "outbounds": [<outbound>]
}
```

**Hysteria2 出站:**
```json
{
    "type": "hysteria2",
    "server": "<address>",
    "server_port": <port>,
    "password": "<password>",
    "tls": {
        "enabled": true,
        "server_name": "<sni>",          // 注意: 是 server_name 不是 sni
        "insecure": true,               // 注意: 是 insecure 不是 allowInsecure
        "alpn": ["h3"]
    },
    "up_mbps": 100,                     // 可选
    "down_mbps": 100,                   // 可选
    "obfs": {                           // 可选, 仅当 cfg.obfs 存在
        "type": "salamander",
        "password": "<obfs_password>"
    }
}
```

**TUIC 出站:**
```json
{
    "type": "tuic",
    "server": "<address>",
    "server_port": <port>,
    "uuid": "<uuid>",
    "password": "<password>",
    "tls": {
        "enabled": true,
        "server_name": "<sni>",
        "insecure": true,
        "alpn": ["h3"]
    },
    "congestion_control": "cubic",      // 可选
    "udp_relay_mode": "native"          // 可选
}
```

**sing-box vs Xray 关键差异表:**
| 概念 | Xray | sing-box |
|------|------|----------|
| 协议字段 | `protocol` | `type` |
| 端口字段 | `port` | `listen_port` (inbound) / `server_port` (outbound) |
| SNI | `tlsSettings.serverName` | `tls.server_name` |
| 证书跳过 | `tlsSettings.allowInsecure` | `tls.insecure` |
| TLS 启用 | `stream.security: "tls"` | `tls.enabled: true` |

### 14.4 协议别名

sing-box 出站构建时接受三个等价的协议名：`hysteria2` / `hy2` / `hysteria`，均映射到 `type: "hysteria2"`。

---

## 十五、服务配置生成器

> 本章描述 `config_generator` 模块如何将数据库中的 service/inbound/outbound/node
> 转化为两个代理进程的配置文件。

### 15.1 端口管理

```python
def is_port_available(port):
    # socket.bind(('127.0.0.1', port)) → 成功则可用

def find_available_port(start=50000, end=60000, exclude=None):
    # 随机尝试 100 次, 调用 is_port_available, 避开 exclude 集合
    # 均失败时抛出 RuntimeError
```

SOCKS 中间端口范围: **50000–60000**。入站端口检查使用相同的 `is_port_available()`。

### 15.2 配置生成主流程

```
generate_service_config(service_id) → dict:
    1. db 获取 service → inbound → outbound
    2. check_inbound_port(inbound.port) → 不可用则返回 error
    3. _get_outbound_node(outbound):
       - single: config_json.node_id → db 查节点
       - auto:   outbound_nodes[0] (取 priority 最小)
    4. find_available_port() → socks_port
    5. _build_xray_inbound(inbound, socks_port) → xray_in 配置
    6. _build_outbound_config(node, socks_port, bin_type) → outbound 配置
    7. 返回 {success, service_name, config_dir, xray_in, outbound_bin, outbound_config, socks_port, inbound_port, node_name}
```

### 15.3 出站配置分发

```python
_build_outbound_config(node, socks_port, bin_type):
    bin_type == 'xray'     → _build_xray_outbound
    bin_type == 'sslocal'  → _build_sslocal_outbound
    bin_type == 'sing-box' → _build_singbox_outbound
```

- `_build_xray_outbound`: 从 node.config_json 解出参数，调用 xray.py 的 `_build_outbound` + `_build_stream_settings`，包装为完整 `{inbounds: [{socks}], outbounds: [...]}` 结构
- `_build_sslocal_outbound`: 直接调用 `generate_sslocal_config(node, socks_port)`，返回扁平 JSON
- `_build_singbox_outbound`: 直接调用 `generate_singbox_config(node, socks_port)`

### 15.4 配置文件命名

```
save_service_config(service_name, xray_in, outbound_bin, outbound_config):
    → config/<service_name>/xray_in.json
    → config/<service_name>/<bin_type>_out.json      # xray_out.json / sslocal_out.json / sing-box_out.json
```

注意文件名包含 `_in` / `_out` 后缀区分方向。

---

## 十六、test.sh 输入输出协议

> checker 模块通过 subprocess 调用此脚本，必须严格遵循以下接口。

### 16.1 TCP Ping

```
调用: bash scripts/test.sh tcp_ping <address> <port> <timeout> <tag>

stdout (成功):
    {"success": true, "latency_ms": <int>}

stdout (失败):
    {"success": false, "error": "connection failed or timed out"}

实现: Python socket.connect() 计时
```

### 16.2 URL Test

```
调用: echo '<json>' | bash scripts/test.sh url_test

stdin JSON (7 个字段, 缺一不可):
{
    "config_path":   "/absolute/path/to/temp/config.json",
    "bin_type":      "xray" | "sslocal" | "sing-box",
    "bin_path":      "/absolute/or/relative/path/to/binary",
    "local_port":    <int>,        # SOCKS5 监听端口
    "test_url":      "http://...",
    "curl_timeout":  <int>,        # 秒
    "tag":           "ph_<node_id>_<timestamp>"   # 唯一标识, 用于清理
}
```

脚本行为:
```
1. 读取 stdin JSON, 提取 7 个字段
2. 解析 bin_path: 相对路径 → 基于 scripts/../ 转为绝对路径
3. 检查二进制存在, 不存在则 chmod +x
4. PID 文件: {config_path}.pid
5. 按 bin_type 构建启动命令:
   xray:     <bin> run -config <config>
   sslocal:  <bin> -c <config>
   sing-box: <bin> run -c <config>
6. export PATH="$bin_dir:$PATH"  (sslocal 需要找到同目录的 obfs-local)
7. setsid <cmd> & → 写入 PID 文件
8. wait_for_port(local_port, 15s, 0.5s 间隔)
9. curl --socks5-hostname 127.0.0.1:<port> --connect-timeout 3 --max-time <curl_timeout> <test_url>
10. cleanup_process_tree (三层清理):
    a. 获取进程 PGID → kill -TERM/-KILL 进程组
    b. pgrep -af <tag> | grep -v test.sh → xargs kill -KILL
    c. pgrep -af <config_filename> | grep -v test.sh → xargs kill -KILL
    d. rm -f pid_file config_path
11. HTTP 2xx/3xx → 成功; 其他 → 失败
```

stdout (成功):
```json
{"success": true, "latency_ms": <int>, "http_code": <int>}
```

stdout (失败):
```json
{"success": false, "error": "<reason>", "http_code": <int>, "latency_ms": <int>}
```

有效 HTTP 状态码: `200, 204, 301, 302, 307, 308`。

### 16.3 Python 解释器检测

脚本开头检测可用的 Python (先 `python3` 后 `python`)，且验证 `json` 模块可用。两者都失败时输出错误 JSON 并退出。

---

## 十七、WebLogger 实现规范

### 17.1 核心机制

```python
class WebLogger:
    logs:  deque(maxlen=500)            # 线程安全队列
    lock:  threading.Lock()
    
    __init__: 保存 sys.stdout/stderr 引用, 替换为 LogWriter
    add():    构造 {time, level, module, message}, 追加到 deque
    get_logs(since): 返回 since 索引之后的日志列表
    restore(): 恢复 sys.stdout/stderr
```

### 17.2 stdout/stderr 拦截

```python
class LogWriter:
    write(text):
        1. self.original.write(text)        # 输出到真实终端
        2. text.strip() → 若为空则跳过
        3. 解析 [...] 提取模块名 (无 [...] 则用 "system")
        4. self.logger.add(level, module, text)
    flush():    → self.original.flush()
    fileno():   → self.original.fileno()    # 部分库依赖此方法
```

**效果**: 任何 `print()` 或第三方库的 stdout 输出都会被自动捕获到 Web 日志，无需显式调用 `add()`。

### 17.3 模块级单例

```python
web_logger = WebLogger()           # 全局实例
log(level, module, message)        # 便捷函数 → web_logger.add(...)
```

### 17.4 Werkzeug 日志抑制

```python
logging.getLogger('werkzeug').setLevel(logging.ERROR)
```

必须在 `app.run()` 之前执行，否则每次 HTTP 请求都会产生日志 → 轮询日志循环。

---

## 十八、API 响应规范

### 18.1 统一错误格式

所有 API 错误响应遵循:
```json
{"success": false, "message": "<error description>"}
```

### 18.2 HTTP 状态码约定

| 状态码 | 场景 |
|--------|------|
| 200 | 正常响应 |
| 400 | 参数缺失或无效 |
| 401 | 未认证 |
| 404 | 资源不存在 |
| 409 | 冲突（如检测任务正在运行） |

### 18.3 密码脱敏

- `GET /api/settings` 返回密码时用 `"******"` 替代
- `POST /api/settings` 收到 `"******"` 时不更新密码字段
- 空字符串 `""` 表示禁用认证
