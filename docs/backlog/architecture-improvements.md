# ProxyHub v2 — 当前软件与文件结构评估

> 评估日期：2026-08-24
> 评估对象：当前仓库实际代码，而不是早期目标结构。
> 相关问题清单：[known-issues.md](known-issues.md)
> 结构优化状态：第 4 节对应重构已按 [structure-refactor-plan.md](structure-refactor-plan.md) 执行；部署优化延期，测试目录已删除，文档结构后续再维护。

## 1. 总体判断

当前结构对于一个单机、自托管、小团队维护的 Flask 控制面来说，**总体合理，也采用了主流的基础模式**：应用工厂、Blueprint、业务编排层、SQLite 数据层、外部系统适配包和模板页面的边界都能辨认，没有必要为了“主流”改成大型框架或引入微服务。

主要问题不是技术选型错误，而是项目从设计时的小体量继续增长后，部分“先保持单文件”的决定已经到达拆分时机；部署、测试隔离和文档同步也落后于功能实现。

综合评价：

| 维度 | 评价 | 说明 |
|---|---|---|
| 技术选型 | 合理 | Flask + SQLite + Jinja2 + sing-box 很适合当前规模和用途 |
| 分层方向 | 基本清晰 | Web、业务、DB、parser、singbox 已形成单向依赖主干 |
| 文件组织 | 可用但开始拥挤 | `routes.py`、`services.py` 和内联前端已超过原拆分阈值 |
| 可测试性 | 纯函数层较好，边界层不足 | parser/protocol/config 好测，API/DB/process 缺少隔离测试 |
| 部署成熟度 | 偏开发态 | Flask 开发服务器、依赖未锁、镜像依赖源码 bind mount |
| 可维护性 | 中等 | 小团队可维护，但文档漂移和大文件会持续增加修改成本 |

## 2. 当前实际结构

```text
proxyhub/
├── app/
│   ├── __init__.py          # Flask 应用工厂和 Blueprint 注册
│   ├── auth.py              # 会话认证
│   ├── pages.py             # 页面路由
│   ├── routes.py            # 47 个 API 端点，505 行
│   ├── services.py          # 订阅、进程、服务 selector 编排，357 行
│   ├── common/
│   │   └── checker.py       # 节点检查和内存任务状态
│   ├── settings.py          # 设置持久化和运行路径
│   ├── logger.py / utils.py
│   ├── db/                  # SQLite 连接、schema、按实体 CRUD
│   ├── parser/              # 按协议拆分的订阅解析器
│   └── singbox/             # config/process/protocol/clash/upgrade 适配层
├── templates/               # 桌面模板 + 477 行移动端单文件 SPA
├── test/                    # 单元测试与手工冒烟脚本混放
├── docs/                    # 设计和接口文档
├── data/ / logs/            # 本地运行时状态，已 gitignore
├── Dockerfile / docker-compose.yml
└── run.py
```

## 3. 做得合理且应保留的部分

### 3.1 Flask 应用工厂和 Blueprint

`create_app()` 负责创建应用、注册认证/页面/API Blueprint 和初始化数据库，这是 Flask 项目常用模式。页面路由与 API 路由分开也合理。后续只需继续细分 API Blueprint，不必更换框架。

### 3.2 `parser/` 和 `singbox/` 的包边界

- `parser/` 按协议拆文件，符合“增加协议 = 增加模块”的扩展方式。
- `singbox/` 聚合配置翻译、进程管理、Clash API 和升级逻辑，外部系统边界清晰。
- `protocol.py`、`config.py` 以纯函数为主，已经证明易于单元测试。

这两部分是当前最健康的结构，不建议合并回大文件。

### 3.3 SQLite 数据层

当前规模使用 SQLite 和显式 SQL 是务实选择。按实体拆 CRUD 文件、开启外键、使用事务完成订阅节点 diff，都比在小项目中过早引入复杂 ORM 更直接。

短期应增加迁移机制和测试，而不是为了形式改成 ORM。

### 3.4 单体应用和单一 sing-box 进程

控制面、数据库和引擎适配仍属于一个部署单元，保持模块化单体比拆微服务更合理。单一 sing-box 常驻进程也与产品定位一致。

## 4. 已到优化时机的部分

### 4.1 API 路由文件过大

早期 `structure.md` 预计 routes 不超过 200–300 行，但当前 `app/routes.py` 已有 505 行和 47 个 API 端点，同时承担：

- sing-box 生命周期；
- subscription/node/inbound/outbound/service CRUD；
- 设置和升级；
- 节点检查任务；
- 日志下载。

建议按业务域拆 Blueprint，而不是按 GET/POST 等技术动作拆：

```text
app/web/
├── pages.py
├── auth.py
└── api/
    ├── __init__.py          # 注册或聚合 Blueprint
    ├── runtime.py           # status/start/stop/restart/logs/upgrade
    ├── subscriptions.py
    ├── nodes.py
    ├── routing.py           # inbounds/outbounds/services
    └── settings.py
```

这是当前最有收益的结构性拆分。仍可保留相同 URL，不影响前端。

### 4.2 `services.py` 混合了三个业务边界

当前文件同时处理：

1. 订阅 HTTP 拉取、解码、解析和同步；
2. DB → sing-box 配置 → 进程启停；
3. 单个服务 selector 的启动、停止和手动切换。

建议拆成小包或三个明确模块：

```text
app/services/
├── subscriptions.py        # refresh/fetch/decode
├── runtime.py              # apply_config/start/stop/restart/status
└── routing.py              # start/stop/switch/get_service_status
```

`app/singbox/` 仍只负责技术适配，业务规则留在 services，依赖方向不变。

### 4.3 内联前端已经超过“无构建小页面”的舒适区

不使用 React/Vue 和前端构建链仍然合理，但“所有 CSS/JS 内联 HTML”在当前规模下维护成本偏高：桌面基础模板 328 行，多个页面 200–500 行，移动端单文件 477 行。

建议保持原生 JavaScript，不引入框架，只把共享资产移到静态文件：

```text
static/
├── css/app.css
└── js/
    ├── api.js
    ├── ui.js
    ├── polling.js
    └── pages/*.js
```

这样仍然没有 Node/npm/构建步骤，却能获得浏览器缓存、语法检查、独立测试和更小的模板 diff。如果短期页面不再增长，也可以暂缓。

### 4.4 设置与运行路径在 import 阶段固化

`settings.py` 在 import 时读取并可能写入文件，logger 也在 import 时创建日志；路径常量随后被多个模块直接导入。这种方式简单，但使测试隔离、环境覆盖和多实例配置困难。

建议逐步改为 Flask config/配置对象：

- 环境变量只决定启动配置；
- `DATA_DIR`、`LOGS_DIR`、binary path 通过应用配置传递；
- 测试创建 app 时注入临时目录；
- 不要求立即引入复杂配置库。

### 4.5 数据库请求结束清理

thread-local 连接原先没有注册 Flask teardown，现已补充请求结束清理。

数据库数据量只有约 100–200 条，不维护 schema version 或自动 migration。未来表结构变化时采用“备份/导出旧数据库 → 重新初始化 → 导入少量数据”的方式处理。

### 4.6 内存任务状态缺少生命周期

节点批量检查的 `_tasks` 和延迟结果存在进程内存中，没有 TTL/数量上限。小规模短期运行问题不大，但长期运行会积累任务，重启也会丢失状态。

当前规模最多约 50–100 个节点，内存占用有限。本项决定暂不修改；只有任务数量或运行模式明显扩大后再重新评估。

## 5. 部署结构评估

> 决定：暂不修改。当前单人使用场景优先保留 Docker 下通过宿主仓库 `git pull` 快速更新的方式，等软件稳定后再评估生产化镜像。

### 5.1 当前方式

- Dockerfile 只安装依赖，没有复制应用代码。
- compose 通过 `.:/opt/proxyhub` 挂载整个仓库后才能运行。
- `run.py` 使用 Flask 自带服务器并固定 8080。

这属于常见的开发/自用部署方式，但不是可独立发布的生产镜像：单独执行镜像没有应用源码，宿主代码会完全覆盖容器工作目录，部署结果也依赖 checkout 状态。

### 5.2 建议目标

- Docker build 时 `COPY app/ templates/ run.py`，镜像本身可运行；
- 只挂载 `/opt/proxyhub/data` 和 `/opt/proxyhub/logs`；
- 用 Gunicorn 等 WSGI server 启动 Flask；
- sing-box binary 可在镜像构建时固定版本安装，或继续作为 data 中可升级资产，但需明确唯一来源；
- 增加容器 healthcheck，至少检查 Web status 和 sing-box 期望状态。

如果项目始终只在可信主机上由单用户运行，以上可以分阶段做，不必一次完成。

## 6. 测试结构评估

> 决定：当前测试代码不再维护，`test/` 已删除；不创建 `tests/` 或 `scripts/`。结构变更使用一次性检查和人工冒烟验收，不在仓库保留测试资产。

## 7. 文档结构评估

> 决定：已先采用 `docs/archive/` 与 `docs/backlog/` 的简易分类，后期有需要时再继续维护，不在本轮扩大调整。

当前文档记录很丰富，但存在“设计稿、实施计划、实际状态”混在一起的问题。例如：

- `structure.md` 仍称结构“待执行迁移”，实际大部分已完成；
- `progress.md` 仍把 checker、认证和前端列为待实现，实际代码已经存在；
- `design.md`、`refer.md` 中部分 cache、stop 和路径决策互相不完全一致。

建议将文档分为三类并在页首明确状态：

```text
docs/
├── architecture/           # 当前有效架构与 ADR
├── reference/              # API、设置、协议等当前参考
├── operations/             # 安装、升级、备份、排错、验收
└── archive/                 # 历史设计和已完成计划
```

不建议现在立即搬动所有文档，避免制造大量失效链接。第一步只需给旧文档加“历史/已过期”提示，并建立一个当前文档索引。

## 8. 推荐的渐进式目标结构

```text
proxyhub/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── web/
│   │   ├── auth.py
│   │   ├── pages.py
│   │   └── api/             # 按业务域拆 Blueprint
│   ├── services/            # subscription/runtime/routing 编排
│   ├── db/                  # 保持当前实体拆分
│   ├── parser/              # 保持
│   ├── singbox/             # 保持
│   ├── common/
│   │   └── checker.py
│   └── utils.py
├── templates/
├── static/                  # 原生 CSS/JS，无构建步骤
├── docs/
├── data/ / logs/
└── Dockerfile / compose / run.py
```

这个目标仍是模块化单体，没有引入不必要的 ORM、消息队列、前端框架或微服务。

## 9. 推荐实施顺序

第 4 节结构优化已经完成，执行与验收记录见 [structure-refactor-plan.md](structure-refactor-plan.md)。下一阶段只处理 [known-issues.md](known-issues.md) 中的业务问题；部署、测试体系、文档深度整理和内存生命周期均按上述决定延期或取消。

## 10. 最终结论

- **是否合理：**合理，核心边界和选型符合项目规模。
- **是否主流：**后端基础模式主流；内联大型前端和依赖源码 bind mount 的镜像更偏个人项目/开发态。
- **是否有优化空间：**有，优先级最高的是核心路由正确性和测试隔离，其次才是拆文件和部署标准化。
- **是否需要大重构：**不需要。建议以保持 API 不变的渐进拆分为主。
