# ProxyHub Structure Refactor Plan

> 建立日期：2026-08-24
> 状态：待确认，尚未执行
> 范围：只做项目结构优化，不修复 `known-issues.md` 中的业务问题

## 1. 目标

本轮把当前已经偏大的扁平文件拆成清晰的模块化单体结构，同时保持现有功能、URL、数据库和 Docker 更新方式不变。

核心目标：

1. 按业务域拆分 Web/API 路由。
2. 按业务职责拆分 service 层。
3. 将大型内联 CSS/JavaScript 抽到 `static/`，继续使用原生前端且不引入构建工具。
4. 分离运行配置与用户设置，为路径注入和生命周期管理打基础。
5. 增加数据库连接 teardown 和轻量 schema version 基础设施。
6. 删除当前不再维护的测试代码，不创建新的 `tests/` 或 `scripts/`。

## 2. 明确不在本轮执行的内容

### 2.1 不修改部署方式

以下文件和行为保持不变：

- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.override.example.yml`
- 仓库整体挂载到 `/opt/proxyhub`
- 通过宿主机 `git pull` 快速更新代码
- `run.py` 当前启动方式

原因：目前是单人使用，快速更新优先。等功能完全稳定后，再考虑自包含镜像、WSGI server 和只挂载 data/logs。

### 2.2 不修复已知业务问题

本轮不修改 [known-issues.md](known-issues.md) 中登记的问题，包括：

- 空出口池路由语义；
- selector 的 `direct` 成员；
- 订阅解析为 0 时清空旧节点；
- auto-start 实际行为；
- sing-box 启动就绪检查；
- `web_port` 和 `PROXYHUB_HOME` 行为；
- API 参数校验和错误响应。

结构迁移必须原样保留当前行为，避免把结构重构和业务修复混在同一次变更中。

### 2.3 不继续整理历史文档

当前 `docs/archive/` 与 `docs/backlog/` 的简易分类保持不变。除新增本方案和维护索引外，不继续移动或改写历史文档。

### 2.4 不引入额外技术栈

不引入：

- React、Vue、Node/npm 或前端构建工具；
- SQLAlchemy、Alembic；
- Redis、Celery 或消息队列；
- 微服务拆分。

### 2.5 不修改内存状态生命周期

当前使用规模约 50–100 个节点，checker task 和 latency store 的内存占用有限。本轮不增加 TTL、容量限制或清理逻辑，保持 `app/checker.py` 与 `app/utils.py` 的现有内存状态语义。

## 3. 目标目录结构

```text
proxyhub/
├── app/
│   ├── __init__.py
│   ├── config.py                 # 运行路径和应用级配置
│   ├── settings.py               # setting.json 用户设置持久化
│   ├── logger.py
│   ├── checker.py
│   ├── utils.py
│   │
│   ├── web/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── pages.py
│   │   └── api/
│   │       ├── __init__.py       # 单一 API Blueprint + 模块注册
│   │       ├── runtime.py        # status/start/stop/restart/logs/upgrade
│   │       ├── subscriptions.py  # subscription CRUD/refresh
│   │       ├── nodes.py          # node CRUD/check/latency
│   │       ├── routing.py        # inbound/outbound/service CRUD 与切换
│   │       └── settings.py       # settings API
│   │
│   ├── services/
│   │   ├── __init__.py           # 兼容性再导出
│   │   ├── subscriptions.py      # fetch/decode/refresh/apply diff
│   │   ├── runtime.py            # apply config + sing-box lifecycle
│   │   └── routing.py            # service selector control/status
│   │
│   ├── db/                       # 保持当前实体拆分
│   ├── parser/                   # 保持当前协议拆分
│   └── singbox/                  # 保持当前技术适配边界
│
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── route.html
│   ├── subscriptions.html
│   ├── nodes.html
│   ├── inbounds.html
│   ├── outbounds.html
│   ├── settings.html
│   └── mobile/index.html
│
├── static/
│   ├── css/
│   │   ├── app.css
│   │   ├── login.css
│   │   └── mobile.css
│   └── js/
│       ├── common.js
│       ├── route.js
│       ├── subscriptions.js
│       ├── nodes.js
│       ├── inbounds.js
│       ├── outbounds.js
│       ├── settings.js
│       └── mobile.js
│
├── docs/
│   ├── README.md
│   ├── archive/
│   └── backlog/
│
├── data/ / logs/
├── Dockerfile
├── docker-compose.yml
├── docker-compose.override.example.yml
├── requirements.txt
├── setup.sh
└── run.py
```

目标结构中不存在 `test/`、`tests/` 或 `scripts/`。根目录 `setup.sh` 保留，它是当前 venv 初始化入口，不属于待删除的 scripts 目录。

## 4. 详细修改方案

### 4.1 Web 与 API 路由拆分

当前文件：

- `app/auth.py`
- `app/pages.py`
- `app/routes.py`

目标：

- 移到 `app/web/`。
- API 使用一个共享 Blueprint，端点实现分散到五个业务模块。
- 所有 URL、HTTP method、endpoint 行为和认证规则保持不变。
- `app/__init__.py` 只负责创建 app、初始化基础设施并注册 Blueprint。

API 分配：

| 模块 | 端点范围 |
|---|---|
| `runtime.py` | `/api/status`、sing-box start/stop/restart、upgrade、logs |
| `subscriptions.py` | `/api/subscriptions*` |
| `nodes.py` | `/api/nodes*`，含 check task 和 latency |
| `routing.py` | `/api/inbounds*`、`/api/outbounds*`、`/api/services*` |
| `settings.py` | `/api/settings` |

兼容策略：

- 前端 URL 不变。
- 不保留旧 `app/routes.py`、`app/pages.py`、`app/auth.py` 空壳；所有仓库内 import 一次性更新。
- 迁移前后比较 Flask `url_map`，端点数量、path 和 method 必须一致。

### 4.2 Service 层拆分

当前 `app/services.py` 拆为：

| 新模块 | 现有职责 |
|---|---|
| `services/subscriptions.py` | `refresh_subscription`、fetch、userinfo、decode |
| `services/runtime.py` | `apply_config`、全局 start/stop/restart/status |
| `services/routing.py` | service start/stop/restart/switch/status |

`app/services/__init__.py` 再导出现有公共函数名，作为短期兼容入口。新的 API 模块优先从具体 service 模块导入，避免继续依赖聚合模块。

本轮只移动代码和调整 import，不修改函数算法、返回结构、日志文字和异常语义。

### 4.3 前端静态资源抽离

处理方式：

- `templates/base.html` 的公共 CSS 移到 `static/css/app.css`。
- `base.html` 的公共 JavaScript 移到 `static/js/common.js`。
- 每个桌面页面的 `{% block extra_js %}` 内容分别移动到同名 JS 文件。
- login 和 mobile 的独立样式、脚本分别移动到 `login.css`、`mobile.css`、`mobile.js`。
- 模板通过 `url_for('static', filename='...')` 引入文件。

保持不变：

- HTML DOM id/class；
- 全局函数名称和调用顺序；
- localStorage key；
- 轮询时间；
- API URL 和 payload；
- 桌面端/移动端跳转逻辑。

不使用 ES module 或打包器，避免脚本作用域变化带来额外风险。

### 4.4 配置职责拆分

新增 `app/config.py`，承载：

- 项目根目录和 data/log/bin/config/db 路径定义；
- 协议、sing-box 参数等应用级常量；
- `create_app()` 可选配置覆盖的基础结构。

`app/settings.py` 只保留：

- `DEFAULT_SETTINGS`；
- `setting.json` 的读写；
- `get_setting`、`set_setting`、`update_settings` 等用户设置 API。

兼容和范围限制：

- 默认运行路径保持当前值。
- 本轮不启用 `PROXYHUB_HOME`，不修改 `web_port` 启动行为，避免提前修复 KI-007。
- 原有模块统一改从 `app.config` 导入运行常量，不通过 Flask `current_app` 强耦合底层模块。
- 允许 `create_app(config_overrides=None)` 为未来隔离运行提供入口，但生产默认行为不变。
- logger 的初始化从 import 副作用逐步收敛到 app 初始化；公共 `log` 对象名称不变。

### 4.5 数据库生命周期与 schema version

修改内容：

1. 在 Flask app 上注册 `teardown_appcontext`，请求结束时调用 `close_db()`。
2. 使用 SQLite `PRAGMA user_version` 记录 schema 版本。
3. 当前 schema 定义为 version 1；已有 version 0 数据库完成表初始化后只标记为 version 1，不删除或重建业务表。
4. 预留按版本顺序执行 migration 的函数结构，但本轮没有业务字段迁移。

不引入 ORM 或 Alembic，不改变现有表、外键和 sentinel 数据。

### 4.6 删除测试相关目录

删除当前仓库的 `test/` 及其全部文件。

- 当前实际目录名是单数 `test/`，不是 `tests/`。
- 不创建新的 `tests/`。
- 当前没有 `scripts/`，本轮也不创建。
- 不删除 `setup.sh`。
- 删除测试后同步移除文档中把测试套件描述为当前资产的内容，仅在 archive 中保留历史记录。

## 5. 实施顺序

每个阶段完成后先做静态验证，再进入下一阶段。

### Phase 1：建立新包并拆 service

1. 创建 `app/services/`。
2. 原样迁移三个职责模块。
3. 建立兼容再导出。
4. 更新 import，删除 `app/services.py`。

### Phase 2：拆 Web/API

1. 创建 `app/web/api/`。
2. 迁移 auth/pages/API handlers。
3. 更新 `create_app()` 注册方式。
4. 比较迁移前后的 route map。
5. 删除旧三个扁平路由文件。

### Phase 3：抽离静态资源

1. 创建 `static/css` 和 `static/js`。
2. 先抽公共 CSS/JS。
3. 再逐页抽离脚本和移动端资源。
4. 检查所有模板可渲染、static URL 可访问。

### Phase 4：配置与数据库生命周期

1. 新增 `app/config.py` 并更新常量 import。
2. 收敛 settings/logger 初始化职责。
3. 注册 DB teardown 和 schema version。

### Phase 5：删除测试目录并更新当前文档

1. 删除 `test/`。
2. 确认不存在 `tests/` 和 `scripts/`。
3. 更新 `docs/README.md` 与本方案状态。
4. 不改 `known-issues.md` 条目内容。

## 6. 验收方案

由于本轮明确删除仓库内测试代码，验收使用一次性命令和人工冒烟，不新增测试文件或 scripts。

### 6.1 静态验收

- `python3 -m compileall -q app run.py`
- 所有 Python import 成功。
- Flask route map 与重构前一致：47 个 API route，7 个页面 route，2 个认证 route。
- 仓库不存在对旧模块 `app.routes`、`app.pages`、`app.auth`、单文件 `app.services` 的引用。
- 所有模板引用的 static 文件存在。
- `git diff --check` 通过。

### 6.2 只读/隔离冒烟

- 创建 Flask app 成功。
- 登录页、桌面页面和移动页面可以渲染。
- `/api/status`、各列表 GET API 返回 JSON。
- 使用临时配置覆盖验证 app 初始化不会写入真实 data（若 Phase 4 的覆盖入口已完成）。
- 从当前数据库构建出的 sing-box config 在重构前后内容一致，不启动进程、不修正已知配置语义。

### 6.3 浏览器人工验收

- 页面样式与重构前一致。
- modal、确认框、轮询、缓存、移动端跳转正常。
- 新增/编辑表单仍发送相同 API payload。
- static 文件均返回 200，无浏览器 JavaScript 语法错误。

### 6.4 范围验收

- Docker 和 compose 文件无 diff。
- `run.py` 启动语义无变化。
- `known-issues.md` 无业务条目修改。
- 不包含 KI-001 至 KI-008 的功能修复。
- 不存在 `test/`、`tests/`、`scripts/`。

## 7. 风险与回退

| 风险 | 控制方式 |
|---|---|
| 路由漏注册或 method 改变 | 重构前后导出 route map 做逐项比较 |
| service import 循环 | API 从具体 service 模块导入；`services/__init__.py` 只做再导出 |
| JS 抽离后加载顺序变化 | `common.js` 固定先加载，页面脚本在 DOM 后加载，不启用 module |
| static 抽离造成样式差异 | 不改 CSS 内容，只移动；逐页浏览器对照 |
| 配置拆分改变运行路径 | 默认值逐项对照，明确不启用 `PROXYHUB_HOME` |
| DB version 误处理旧数据 | 只对现有 schema 标记 version 1，不执行 destructive migration |
| 删除测试后缺少回归保护 | 本轮采用 route map、compile、配置一致性和人工冒烟；未来是否恢复测试另行决定 |

任何阶段出现行为差异时，优先回退该阶段，不继续叠加下一阶段修改。

## 8. 确认项

开始执行前确认以下约束：

- [ ] 接受 `app/web/`、`app/services/` 和 `static/` 的目标结构。
- [ ] 接受删除当前 `test/` 全部文件，且不新建 `tests/`。
- [ ] 接受当前没有 `scripts/`，本轮保持不存在；保留根目录 `setup.sh`。
- [ ] 接受 Docker、compose 和 `run.py` 部署语义暂不修改。
- [ ] 接受本轮只做结构迁移，不修复 `known-issues.md` 中的业务问题。
- [ ] 接受使用 SQLite `PRAGMA user_version = 1` 建立轻量 schema version 基线。
