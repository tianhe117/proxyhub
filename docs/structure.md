# 目录结构优化方案

> 层级：全局。本文是目录结构重构的定案稿，承接[顶层设计](design.md)核心决策。
> 状态：✅ 定案，待执行迁移。

## 1. 原则

**包是为了聚拢真有多模块内聚的东西，不是为了占位「将来要分层」。**

判据只有一条：这个层有没有「多个内聚模块、加新成员 = 加文件」的模式。

- **有** → 开包（一文件一模块，各不相依，加协议/加表 = 加文件不改其他文件）
- **没有** → 单文件（先写扁，涨到 300+ 行再拆包，不预创占位）

预创空包占位有两个害处：目录树看起来比实际复杂（误导「8 层都铺好了」），且方案未定就占位，后续改方案要连目录一起改。

## 2. 目标结构

```
proxyhub/
├── app/
│   ├── __init__.py          # create_app() 工厂 + 蓝图注册
│   ├── settings.py          # 常量 + setting.json 持久化
│   ├── logger.py            # 文件日志（独立，import 时建文件）
│   ├── utils.py             # common + validators + latency（纯叶子工具）
│   ├── routes.py            # Flask 路由（Blueprint，单文件）
│   ├── services.py          # 业务编排（订阅/节点/出站，扁平）
│   ├── checker.py           # tcp_check + url_check（扁平）
│   ├── scheduler.py         # failover / fallback（扁平）
│   │
│   ├── db/                  # 包：数据层，一表一文件
│   │   ├── __init__.py      # get_db / close_db / init_db + 再导出
│   │   ├── database.py      # 连接管理 + schema + 哨兵行
│   │   ├── subscription.py
│   │   ├── node.py
│   │   ├── inbound.py
│   │   ├── outbound.py
│   │   ├── service.py
│   │   └── references.py    # 反向引用查询（跨表，例外）
│   │
│   ├── singbox/             # 包：sing-box 集成层
│   │   ├── __init__.py      # 再导出公共 API
│   │   ├── protocol.py      # DB dict → sing-box dict（纯函数）
│   │   ├── config.py        # 组装 config.json（纯函数）
│   │   ├── process.py       # start / stop / restart
│   │   ├── upgrade.py       # 下载 / 升级二进制
│   │   └── clash.py         # clash_api 客户端（← client.py 改名）
│   │
│   └── parser/              # 包：订阅解析，一协议一文件
│       ├── __init__.py      # parse_all()：decode → 分发 → 过滤
│       ├── base.py          # decode_base64 / filter_lines / parse_kv_params
│       ├── ss.py
│       ├── vmess.py
│       ├── vless.py
│       ├── trojan.py
│       ├── hysteria2.py
│       └── tuic.py
│
├── templates/
│   └── base.html            # 单页前端，CSS/JS 内联
│
├── test/                    # pytest，一模块一测试文件
│
├── data/                    # 运行时数据（gitignore）
│   ├── bin/                 # sing-box 二进制 + libcronet.so
│   ├── config.json
│   ├── setting.json
│   ├── seed.json
│   └── proxyhub.db
│
├── logs/                    # 日志（gitignore，每次启动一个文件）
│
├── docs/                    # 设计稿
│
├── Dockerfile
├── docker-compose.yml
├── docker-compose.override.example.yml
├── requirements.txt         # flask
├── setup.sh                 # venv 模式一键初始化
├── run.py                   # 唯一入口
├── .gitignore
└── .dockerignore
```

## 3. 改动清单（相对现状）

| # | 改动 | 理由 |
|---|------|------|
| 1 | **删空包** `app/checker/`、`app/scheduler/`、`app/services/`、`app/routes/` | 只有 1 行占位 `__init__.py`，方案未定就占位会误导；要写时再 `mkdir`，写完直接是单文件 |
| 2 | `app/utils/` 包 → `app/utils.py` 单文件 + `app/logger.py` 独立 | utils 4 文件加起来 151 行，拆包纯过度分解；logger 因 import 时建文件是副作用，单独成模块隔离 |
| 3 | `app/singbox/client.py` → `app/singbox/clash.py` | clash_api 就是 sing-box 的 HTTP API，放 singbox/ 包对；改名 `clash` 看名字即知是 clash_api 适配器，比 `client` 泛名清晰 |
| 4 | 新建 `app/parser/` 包 | 订阅解析 6 协议各有 URI 格式，一协议一文件，加协议 = 加文件，内聚真实 |
| 5 | `db/subscription.sync_nodes` → `apply_node_diff`（或 `replace_nodes_by_name`） | 业务层 `services.sync_nodes` 是完整流程（拉取→解析→调 db），db 层是 name diff 原语，同名撞车；db 层改名，把 `sync_nodes` 让给业务层 |
| 6 | `routes/` 不开包，用 `app/routes.py` 单文件 | 前端单页内联 CSS/JS，路由大概率 15-25 端点，一个 Blueprint 足够；涨大再拆 |

### 3.1 判据应用说明

| 层 | 处置 | 判据 |
|----|------|------|
| `db/` | **包** | 7 张表各有 CRUD，一表一文件，内聚真实 |
| `singbox/` | **包** | 6 模块都「跟 sing-box 打交道」，换引擎换整个包，边界干净 |
| `parser/` | **包** | 6 协议各一个 `parse()`，加协议 = 加文件 |
| services / checker / scheduler / routes | **扁平单文件** | 各自大概率不超 200 行，预拆包无收益 |

## 4. 依赖方向

```
routes.py ──▶ services.py ──▶ db / singbox / parser
                    │
                    ├── db.*           （读写 DB）
                    ├── singbox.config （生成 config.json）
                    ├── singbox.process（启停进程）
                    ├── parser.parse_all（解析订阅）
                    └── singbox.clash  （clash_api 测速/切换）

checker.py ──▶ singbox.clash（url_check 调 /delay）
         └──▶ utils（tcp_check 纯 socket）

scheduler.py ──▶ singbox.clash（PUT /proxies/{g} 切节点）

singbox/config.py ──▶ singbox/protocol.py（纯字段翻译）
singbox/process.py ──▶ settings（路径常量）
singbox/upgrade.py ──▶ settings（repo / asset 模式）
```

- `parser/` 与 `singbox/protocol.py` 都不依赖 db / 不做 IO，是叶子纯函数层。
- `services.py` 是唯一横切编排点，向下调 db / singbox / parser，向上被 routes 调。
- `checker.py` / `scheduler.py` 消费 `singbox.clash`，但不调 services（无环）。

## 5. 迁移顺序

按「零风险 → 低风险 → 新建」推进，每步可独立提交：

1. **删空包**（零风险）：删 `checker/`、`scheduler/`、`services/`、`routes/` 四个占位包；`app/__init__.py` 的 `# TODO(Web/route layer)` 留着，写 routes 时再删。
2. **utils 拆平**（低风险）：`utils/common.py` + `validators.py` + `latency.py` 合并成 `app/utils.py`；`logger.py` 移到 `app/logger.py`；更新所有 `from app.utils import log` 的 import（`log` 改从 `app.logger` 导出，`app.utils` 再 re-export 保持兼容）。
3. **singbox/client.py → clash.py**（低风险）：重命名 + 更新 singbox `__init__.py` 的导出。
4. **db.sync_nodes 改名**（低风险）：`db/subscription.py` 内 `sync_nodes` → `apply_node_diff`；当前无调用方（services 还没写），零波及。
5. **建 parser 包**（新建）：按 [parser.md](parser.md) 方案编码 `app/parser/`。
6. **建扁平层文件**（新建）：写 services / checker / scheduler / routes 时直接建单文件，不建包。

## 6. 边界与后续

- **不预创空文件**：services / checker / scheduler / routes 现在都不建，写哪层时再建对应单文件。`app/__init__.py` 的蓝图注册也等 routes 写完再补。
- **拆包阈值**：任一扁平文件超过 300 行且有清晰子边界时，再拆包；不按「将来可能很大」预拆。
- **`clash.py` 归属**：放 singbox/ 包内。它被 checker/scheduler 消费是正常的跨层调用（它们在调 sing-box 的 API），不是归属错位。
- 对应 [顶层设计](design.md) §5 分层规划，本文将其中的 Web/路由层、服务层、健康检查层、调度层从「子包」收敛为「单文件」。
