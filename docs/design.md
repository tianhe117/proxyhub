# ProxyHub v2 — 顶层设计

> 本文是 v2 的**顶层设计**：只立核心决策与整体骨架，各层细节后续逐层细化。
> 旧设计稿归档在 [`refer.md`](refer.md)，复用/重写边界以后续逐层讨论为准。

## 1. 定位

ProxyHub 从「三引擎 + 多进程」收敛为**「单一 sing-box + 常驻进程 + clash_api」**：所有代理协议交给一个 sing-box 进程，Flask 作为控制层只做「配 + 查 + 切」，健康检查拆成「Python 直连预筛 + clash_api 实测」。

## 2. 四个核心决策（锚点）

| # | 决策 | 内容 | 后续分层 |
|---|------|------|---------|
| 1 | **单一 sing-box** | 只用 sing-box 一个工具，覆盖 vmess/vless/trojan/ss/hysteria2/tuic/direct；删 xray / sslocal / obfs-local | 引擎层 |
| 2 | **Flask 前端** | 保留 Flask 作为 Web 层，纯控制（配 db + 调 clash_api，不碰进程） | Web/路由层 |
| 3 | **检查拆两半** | TCP 检查用 Python 库（纯 socket 直连）；URL 检查走 sing-box 的 api（clash_api `/delay`） | 健康检查层 |
| 4 | **一套目录两种跑法** | 目录结构同时兼容 Docker 与直接 venv 运行 | 目录/部署层 |

## 3. 架构总览

```
┌─────────────────────────────────────────────┐
│          sing-box 常驻进程（唯一引擎）         │
│  inbound i{id} ─route─▶ selector g{id}      │
│                          ├─ n{id} 真实节点   │
│                          └─ direct / block   │
│  clash_api: 127.0.0.1:9090                   │
└────────────────┬────────────────────────────┘
                 │ HTTP（查询/测速/切换）
┌────────────────▼────────────────────────────┐
│              Flask（Python 控制层）           │
│  db ──▶ config 生成器 ──▶ config.json        │
│  checker：tcp_check（Python）+ clash_api /delay│
│  调度：failover / fallback = PUT /proxies/{g}│
└─────────────────────────────────────────────┘
```

## 4. 目录结构草案（核心决策 4）

「一套目录，两种跑法」——`data/` + `logs/` 承载一切运行时状态：Docker 里 mount 成 volume，venv 里就是仓库内本地目录。路径不硬编码，由 settings + 环境变量解析。

```
proxyhub/
├── app/                    # Flask 应用包（控制层）
│   ├── __init__.py         # create_app() 工厂
│   ├── settings.py         # 配置持久化（复用，删多引擎字段）
│   ├── db/                 # 数据模型（复用，不变）
│   ├── singbox/            # ★ 所有 sing-box 相关（config+engine+process 合并）
│   │   ├── config.py       # db → config.json（纯函数，好单测）
│   │   ├── process.py      # 单进程 start/stop/restart（无热重载）
│   │   └── client.py       # clash_api client：/delay、PUT/GET /proxies
│   ├── checker/            # tcp_check + url_check（调 singbox.client）
│   ├── scheduler/          # failover/fallback 调度
│   ├── services/           # 业务服务层（订阅/升级/节点/出站）
│   ├── routes/             # pages + api_*
│   └── utils/              # 叶子工具（复用）
├── templates/              # Jinja2 前端：纯 HTML，CSS/JS 内联进 base.html
├── logs/                   # ★ 日志（gitignore；docker=volume）
│   └── YYYY-MM-DD_HHMMSS.log   # 每次启动一个新文件，如 2026-08-17_201500.log
├── data/                   # 运行时数据（gitignore；docker=volume）
│   ├── bin/sing-box        # sing-box 二进制
│   ├── config.json         # 生成的配置
│   └── setting.json        # 应用设置
├── test/                   # pytest
├── Dockerfile              # 多阶段：装 sing-box + Python 依赖
├── docker-compose.yml
├── requirements.txt
├── setup.sh                # 目录占位：venv 模式一键初始化（实现留待部署层细化）
├── run.py                  # 唯一入口（venv + docker 共用）
└── .gitignore
```

### 结构调整说明（2026-08-17 讨论定案）

1. **singbox 包合并**：`config/` + `engine/` + `process/` 合并为 `app/singbox/`。v2 只有一个 sing-box，config 生成、进程启停、clash_api 调用都是「跟 sing-box 打交道」，归到一个包。内部用模块边界隔离——`config.py` 是纯函数，不依赖 `process.py`，测试性不丢。
2. **前端纯 HTML**：删 `static/`，无前端框架、无构建步骤。CSS/JS 全部内联进 `templates/base.html`（现有全局 `showConfirm`/`showMessage`/`closeModal` 与横版 modal 样式即此模式）。
3. **删 scripts/、setup.sh 只占位**：`scripts/` 删除；根目录保留一个 `setup.sh`（venv 模式一键初始化，建 venv + 装 requirements + 建 `data/`/`logs/`），但**仅作目录占位，实现留待部署层细化**。sing-box 二进制 Docker 镜像内置，venv 模式 PoC 阶段手动放置。
4. **日志单独目录**：顶层 `logs/`，与 `data/` 平级；Docker 两个目录各自挂 volume。文件名按进程启动命名 `YYYY-MM-DD_HHMMSS.log`（如 `2026-08-17_201500.log`），每次启动一个新文件。
5. **不用 cache_file**：不启用 sing-box `cache_file`，`data/` 无 cache.db。重启后 selector 直接用 **default 节点**，不自动恢复上次选择（手动选择/failover 结果不跨重启保留）。current node 查询以 clash_api `GET /proxies` 为准。

## 5. 分层规划（待细化）

以下各层在顶层定案后逐层展开（每层一个文件或按需合并，命名以实际细化时为准）：

| 层 | 定位 | 状态 |
|----|------|------|
| 引擎层 | `app/singbox/`：协议面、config 生成、tag 约定（`n/g/i` + id）、clash_api client | ⏳ 待细化 |
| Web/路由层 | Flask 工厂 + routes 分层 + templates（纯 HTML，CSS/JS 内联）+ 认证 | ⏳ 待细化 |
| 健康检查层 | tcp_check（Python 直连）+ url_check（clash_api `/delay`）、`CheckResult` 去 http_code | ⏳ 待细化 |
| 进程管理层 | 单常驻进程 start/stop/restart（无热重载） | ⏳ 待细化 |
| 调度层 | failover / fallback / 手动切节点，统一 `PUT /proxies/{g}` | ⏳ 待细化 |
| 数据层 | db 模型复用（与 sing-box 同构，已外键化） | ⏳ 待细化 |
| 服务层 | 订阅 / 升级（只下 sing-box）/ 节点 / 出站等业务 | ⏳ 待细化 |
| 部署层 | Dockerfile / docker-compose / venv 初始化 | ⏳ 待细化 |

## 6. 复用 / 重写边界（摘要）

> 完整清单见 [`refer.md` §9](refer.md)，此处只列要点，逐层细化时引用。

**复用（资产）**：`db/` 全部、`tcp_check`、`CheckResult`（砍 `http_code`）、`utils/common.py` / `validators.py` / `logger.py` / `latency.py`、`port.is_port_available`、订阅协议 parser、`process._is_running`、settings 持久化机制。

**重写**：engine（三引擎 → `app/singbox/` 单包：config 生成 + 进程管理 + clash_api）、checker url_check（subprocess → clash_api）、service_manager、config_service、routes + 前端。

**删除**：xray / sslocal / obfs-local 三套二进制与配置、临时 Socks5 探测、test 端口池、`proxy_url_check.sh`。
