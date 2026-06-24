# ProxyHub

自托管的代理服务管理面板，提供 Web UI 统一管理多个代理引擎的订阅、节点、入站、出站和服务进程。

## 平台支持

仅支持 **Ubuntu 22.04+ (amd64)**。

## 核心功能

- **订阅管理** — 支持 `vmess://`、`ss://` 链接及 Clash YAML 格式，支持关键字过滤与排除
- **节点管理** — 批量 TCP/HTTP 延迟检测，自定义节点，按订阅分组
- **入站管理** — 定义本地监听协议（HTTP / SOCKS5 / Shadowsocks / VMess）
- **出站管理** — 三种出口策略：直连（direct）、单节点（single）、节点池（auto）
- **服务管理** — 组合入站 + 出站，启动/停止/重启代理进程，支持 auto-start
- **二进制管理** — 从 GitHub Releases 下载/升级代理引擎，查看版本状态
- **实时日志** — Web 端日志面板，stdout/stderr 自动捕获
- **系统信息** — 平台、Python 版本、数据库大小、引擎版本一览
- **一键重启** — 停止所有进程并重启全部 auto-start 服务
- **会话认证** — 用户名/密码登录，session 持久化 30 天，secret_key 固定存储

> **TODO**: 节点自动切换（故障转移）尚未实现，当前节点池仅作静态列表使用，后续版本会加入健康检测驱动的自动切换。

## 支持的代理引擎

| 引擎 | 协议 |
|------|------|
| [Xray](https://github.com/XTLS/Xray-core) | VMess / VLESS / Trojan / Shadowsocks / SSR / AnyTLS / HTTP / SOCKS |
| [shadowsocks-rust](https://github.com/shadowsocks/shadowsocks-rust) | Shadowsocks + obfs 插件 |
| [sing-box](https://github.com/SagerNet/sing-box) | Hysteria2 / TUIC |

## 快速部署

```bash
chmod +x setup.sh
./setup.sh
./venv/bin/python run.py
```

浏览器打开 `http://<server-ip>:8080`，默认用户名 `admin`，默认无密码（直接进入）。

## 项目结构

```
ProxyHub/
├── run.py                       # 应用入口
├── setup.sh                     # 一键部署脚本
├── requirements.txt             # Python 依赖 (flask, pyyaml)
├── README.md
├── docs/DESIGN.md               # 完整设计文档
│
├── app/
│   ├── settings.py              # 配置常量、二进制注册表、协议映射、路径工具
│   ├── logger.py                # WebLogger — 内存日志缓冲 + stdout/stderr 拦截
│   │
│   ├── models/                  # 数据访问层 (SQLite WAL)
│   │   ├── database.py          # 连接管理、初始化、迁移
│   │   ├── setting.py           # 设置 CRUD
│   │   ├── subscription.py      # 订阅 CRUD + 批量节点写入
│   │   ├── node.py              # 节点 CRUD + 分组查询
│   │   ├── inbound.py           # 入站 CRUD
│   │   ├── outbound.py          # 出站 + 节点池 CRUD
│   │   └── service.py           # 服务 CRUD + auto-start 查询
│   │
│   ├── services/                # 业务逻辑层
│   │   ├── auth_service.py      # 会话认证
│   │   ├── subscription_service.py  # 订阅获取、解析 (vmess/ss/clash YAML)、过滤
│   │   ├── node_service.py      # 节点管理 + 验证
│   │   ├── outbound_service.py  # 出站 + 节点池管理 (增删改查/排序/同步)
│   │   ├── service_manager.py   # 服务启动/停止/重启 + auto-start 守护线程
│   │   ├── config_service.py    # 双进程配置生成 (Xray 入站 + 出站引擎) + 端口分配
│   │   └── upgrade_service.py   # GitHub Releases 版本检查 / 下载
│   │
│   ├── engine/                  # 代理引擎 JSON 配置生成
│   │   ├── __init__.py          # build_outbound_config() 统一入口
│   │   ├── xray.py              # Xray (vmess/vless/trojan/ss/ssr/anytls)
│   │   ├── sslocal.py           # shadowsocks-rust (ss + obfs)
│   │   └── singbox.py           # sing-box (hysteria2/tuic)
│   │
│   ├── process/manager.py       # POSIX 进程管理 (setsid/SIGTERM/SIGKILL/PID 文件)
│   │
│   ├── checker/                 # 节点健康检测
│   │   ├── __init__.py          # 编排层 (全局锁、后台线程、任务进度)
│   │   └── script.py            # test.sh 子进程封装
│   │
│   ├── routes/                  # Flask 路由
│   │   ├── __init__.py          # create_app() + auth_required 装饰器
│   │   ├── pages.py             # 页面路由 (dashboard/nodes/outbounds/subscriptions/inbounds/settings/login)
│   │   ├── api_auth.py          # POST /api/auth/login, logout
│   │   ├── api_settings.py      # GET/POST /api/settings, reset
│   │   ├── api_subscriptions.py # CRUD + /refresh
│   │   ├── api_nodes.py         # CRUD + grouped + by-sub + check + check/status + clear
│   │   ├── api_inbounds.py      # CRUD
│   │   ├── api_outbounds.py     # CRUD + 节点池管理 (add/remove/reorder/sync)
│   │   ├── api_services.py      # CRUD + start/stop/restart
│   │   ├── api_bins.py          # GET /api/bins/status
│   │   ├── api_upgrade.py       # check/<bin> + download/<bin>
│   │   ├── api_logs.py          # GET /api/logs?since=N
│   │   └── api_system.py        # GET /info, POST /restart-all, GET /process-count
│   │
│   └── utils/
│       ├── helpers.py           # format_size, split_keywords
│       └── validators.py        # 协议/端口/bin_type 验证
│
├── templates/                   # Jinja2 模板 (纯 HTML/CSS/vanilla JS，无框架)
│   ├── base.html                # 应用外壳 + 全局 CSS 设计系统
│   ├── login.html               # 登录页
│   ├── dashboard.html           # 仪表盘 (运行进程数、服务状态概览)
│   ├── nodes.html               # 节点管理 (分组、延迟检测、批量操作)
│   ├── outbounds.html           # 出站管理 (single/auto/direct + 节点池拖拽排序)
│   ├── subscriptions.html       # 订阅管理 (刷新、节点计数)
│   ├── inbounds.html            # 入站管理
│   └── settings.html            # 设置页 (二进制路径、端口、超时、升级)
│
├── scripts/test.sh              # 节点连通性测试 (TCP ping + URL test)
├── bin/                         # 代理二进制存放 (gitignored)
├── config/                      # 服务运行时配置 (gitignored)
└── data/                        # SQLite 数据库 + PID 文件 (gitignored)
```

## API 概览

| 前缀 | 说明 | 端点 |
|------|------|------|
| `/api/auth` | 认证 | `POST /login`, `POST /logout` |
| `/api/settings` | 设置 | `GET /`, `POST /`, `POST /reset` |
| `/api/subscriptions` | 订阅 | `GET /`, `POST /`, `PUT /<id>`, `DELETE /<id>`, `POST /<id>/refresh` |
| `/api/nodes` | 节点 | `GET /`, `GET /grouped`, `GET /by-sub/<id>`, `POST /`, `PUT /<id>`, `DELETE /<id>`, `POST /clear`, `POST /check`, `GET /check/<task>/status` |
| `/api/inbounds` | 入站 | `GET /`, `POST /`, `PUT /<id>`, `DELETE /<id>` |
| `/api/outbounds` | 出站 | `GET /`, `POST /`, `PUT /<id>`, `DELETE /<id>`, `GET /<id>/nodes`, `POST /<id>/nodes`, `DELETE /<id>/nodes/<pid>`, `POST /<id>/nodes/reorder`, `POST /<id>/nodes/sync` |
| `/api/services` | 服务 | `GET /`, `GET /<id>`, `POST /`, `PUT /<id>`, `DELETE /<id>`, `POST /<id>/start`, `POST /<id>/stop`, `POST /<id>/restart` |
| `/api/bins` | 二进制 | `GET /status` |
| `/api/upgrade` | 升级 | `GET /check/<bin>`, `POST /download/<bin>` |
| `/api/logs` | 日志 | `GET /?since=N` |
| `/api/system` | 系统 | `GET /info`, `POST /restart-all`, `GET /process-count` |

所有错误响应格式为 `{"success": false, "message": "..."}`。

## 技术栈

- **后端**: Python 3 + Flask 3.0+
- **数据库**: SQLite (WAL 模式)
- **前端**: Jinja2 + 纯 HTML/CSS/vanilla JS（无框架）
- **进程管理**: POSIX 信号 (SIGTERM/SIGKILL)、setsid、PID 文件
- **依赖**: `flask`, `pyyaml`

## License

MIT
