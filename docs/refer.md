# ProxyHub v2 — 单一 sing-box 架构设计

## 1. 背景与目标

当前 ProxyHub 是「三引擎 + 多进程」架构：每个 service 起两个进程（inbound + outbound），引擎按协议分发到 xray / sslocal / sing-box，健康检查靠临时进程 + Socks5 探测。

重构方向：**把所有运行面收敛到单一常驻 sing-box 进程**，通过 clash_api 做测速与切换。目标：

- 一个引擎（sing-box）覆盖全部协议，删掉 xray / sslocal / obfs-local 三套二进制与配置生成
- 一个常驻进程，无热重载，只有 start / stop / restart
- 启停服务、failover 切换、手动切节点，**统一成一个操作**：`PUT /proxies/{group}` 切换 selector
- 保留 TCP 检查（纯 Python，与引擎无关）作为廉价预筛；URL 测速改走 clash_api

## 2. 核心架构决策（已定）

| 决策 | 结论 |
|------|------|
| 引擎 | 单一 sing-box，覆盖 vmess/vless/trojan/ss/hysteria2/tuic/direct |
| 进程模型 | 单常驻 sing-box 进程，容器内重启即可 |
| 热重载 | **不要**。配置变更 = 重新生成 config + 重启 sing-box |
| web 框架 | 保留 Flask（轻量够用） |
| 服务状态 | 只有 run / stop（从 selector 指向推导，无 error 态） |
| tag | 复用 db id，加最短前缀区分类型；前端负责解析映射 |
| 节点切换 | 通过 clash_api 查询/下发，Python 侧不再管进程 |

## 3. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                     sing-box 常驻进程                    │
│                                                         │
│  inbound i{id} ──route──▶ selector g{id}                │
│  inbound i{id} ──route──▶ selector g{id}                │
│                           ├─ n{id} (真实节点 outbound)   │
│                           ├─ n{id}                       │
│                           └─ direct / block              │
│                                                         │
│  clash_api: 127.0.0.1:9090                              │
└──────────────┬──────────────────────────────────────────┘
               │ HTTP
┌──────────────▼──────────────────────────────────────────┐
│              Flask 应用（Python 控制层）                 │
│                                                         │
│  db（数据模型，不变）  ──▶  config 生成器 ──▶ config.json │
│  checker：tcp_check（直连）+ clash_api /delay（URL 测速）│
│  scheduler：failover / fallback = PUT /proxies/{group}   │
└─────────────────────────────────────────────────────────┘
```

## 4. 数据模型 → sing-box config 映射

db 模型不变，与 sing-box 结构同构：

| db 表 | sing-box 实体 | tag |
|-------|--------------|-----|
| `nodes.id` | 一个 outbound（协议各 type） | `n{id}` |
| `outbounds.id`（出站组） | 一个 selector | `g{id}` |
| `outbound_nodes.node_id`（池） | selector 的 `outbounds` 列表 | — |
| `outbound_fallback.node_id` | 独立变量（sing-box 不管，调度层维护） | — |
| `inbounds.id` | 一个 inbound | `i{id}` |
| `services` | 一条 route 规则（`inbound: i{id}` → `outbound: g{id}`） | — |

### tag 约定

- 节点：`n{node_id}` → `n1`、`n42`
- 出站组（selector）：`g{outbound_id}` → `g2`
- 入站：`i{inbound_id}` → `i3`

理由：sing-box 的 tag 必须全局唯一，node id 与 group id 会数字冲突，故加单字母前缀区分类型。前端拿到 tag 后 strip 首字母取 id，再查 db 得到可读 name——全数字可读性差由前端解析解决，tag 本身保持最短。

### 固定出站

| tag | type | 用途 |
|-----|------|------|
| `direct` | direct | 直连（服务 stop 时的落点；也是「不走出站」） |
| `block` | block | 丢弃（可选，若需要「硬停」而非「直连」） |

## 5. 服务状态模型（run / stop）

单一进程下，「启停服务」不再是杀进程，而是**切 selector**：

| 状态 | 含义 | 实现 |
|------|------|------|
| run | 服务在代理 | selector `g{id}` 的 `now` 指向真实节点 `n{id}` |
| stop | 服务不代理 | selector `g{id}` 的 `now` 指向 `direct` |

所以**启停 / failover / fallback / 手动切节点，全部统一为 `PUT /proxies/{g{id}}`** 这一个操作，只是切到的目标 tag 不同：

- start service → 切到默认节点
- stop service → 切到 `direct`
- failover → 切到下一个健康节点
- fallback → 切到 `fallback` 节点

> ⚠️ 待确认：stop 用 `direct`（流量直连）还是 `block`（流量丢弃）？取决于「服务停」的语义——是「不代理，但 inbound 还通」还是「完全不通」。默认倾向 `direct`（与现状 `outbound_id=0` 语义一致）。

## 6. 进程管理

`app/process/manager.py` 整个重写为「单进程管理」：

- `start()`：生成 config.json → 起 sing-box → 等 clash_api 就绪
- `stop()`：SIGTERM → SIGKILL（保留现有 `_kill_pid` 的进程组逻辑）
- `restart()`：stop + start
- 状态查询：`GET /proxies` 或进程存活探测

不再有 `_scan_processes` / `get_all_processes` / `has_in_and_out` / per-service 进程识别那套。**`_is_running`（读 /proc/{pid}/stat 判 zombie）可复用。**

## 7. 健康检查（checker）

| 组件 | 现状 | v2 |
|------|------|-----|
| `tcp_check` | 纯 socket 直连，**复用** | 不变 |
| `url_check` | subprocess 起临时进程 + Socks5 + curl | **删除**，改 clash_api `GET /proxies/{tag}/delay` |
| 临时 config 生成 | `_check_url_one` | 删除 |
| test 端口池 55000-60000 | `allocate_ports('test')` | 删除（不再需要临时 Socks5） |
| `proxy_url_check.sh` | bash 脚本 | 删除 |
| `CheckResult.http_code` | curl `%{http_code}`（204） | **删除字段**（clash_api `/delay` 不返回状态码，只返回 delay） |

### clash_api 测速

```
GET /proxies/{n{id}}/delay?url=...&timeout=3000
→ 200 {"delay": 142}        # 存活 + 延迟
→ 504/400 {"message": ...}  # 超时/失败
```

- TCP 先筛：`tcp_check` 失败的节点直接跳过 URL 测速
- 结果喂给现有 `CheckResult` + `utils/latency` 内存 store，字段语义：`url_latency_ms = delay`，`tcp_latency_ms` 保留（tcp_check 产出）

## 8. 调度（failover / fallback）

调度层是「决策大脑」，只调 clash_api 下发，不碰进程：

- 测速算分 → 排序 → 选健康节点 → `PUT /proxies/{g{id}}`
- fallback 节点是调度层的独立变量（db `outbound_fallback` 表），不体现在 sing-box 配置里
- current node 查询：`GET /proxies` 返回每个 selector 的 `now`，即当前生效节点

### 节点选择持久化

sing-box 1.8.0 起 `store_selected` 废弃，改由 `cache_file.enabled` 控制（selector 选择持久化到 cache 文件，重启后恢复）。v2 需开启：

```json
{ "experimental": { "clash_api": { ... }, "cache_file": { "enabled": true } } }
```

## 9. 复用 / 重写清单

### ✅ 确定复用（不改）

| 资产 | 理由 |
|------|------|
| `db/` 全部（database/node/inbound/outbound/subscription/service/references） | 数据模型是核心，与 sing-box 同构，且已外键化 |
| `utils/tcp_check` | 纯 Python，与引擎无关 |
| `CheckResult`（schemas） | 复用，但**砍掉 `http_code` 字段**（clash_api 无状态码） |
| `utils/common.py`、`validators.py`、`logger.py` | 叶子工具，无引擎耦合 |
| `utils/port.py` 的 `is_port_available` | 保留（探 inbound 用户端口是否被占）；`allocate_ports` + 两个端口池删除（单一进程无中间 Socks5 跳） |
| `utils/latency.py` | 内存延迟 store，调度层继续用 |
| 订阅协议 parser（`_parse_vmess_link`/`_parse_ss_link`/`_parse_clash_*` 等） | 纯函数，与执行引擎无关（按后续方案精简协议面 + 下沉 utils） |
| `process/_is_running`（读 /proc 判 zombie） | 单进程管理仍要探测存活 |
| `settings.py` 的 `_store` + `setting.json` 持久化机制 | 配置持久化，保留 |

### ❌ 确定重写

| 资产 | 原因 |
|------|------|
| `engine/xray.py` + `engine/sslocal.py` + `engine/singbox.py` + `engine/service.py` | 三引擎分发 → 单一「db 模型 → config.json」生成器 |
| `process/manager.py`（除 `_is_running`） | 多进程扫描 → 单常驻进程 |
| `checker/checker.py` 的 `url_check`、`checker/service.py` 的 `_check_url_one` | subprocess → clash_api client |
| `services/service_manager.py` | 启停/failover 全改（统一成 selector 切换） |
| `services/config_service.py` | 配置生成逻辑重写 |
| `routes/` + `templates/` | 用户决定重写 |

### ⚠️ 需改后复用

| 资产 | 改动 |
|------|------|
| `settings.py` | 删 `BIN_REGISTRY`（三引擎）、`BIN_REPOS`（含 obfs-local）、`PROTOCOL_BIN_MAP` 简化为协议列表、`SOCKS_PORT_*`/`TEST_PORT_*` 区间；保留路径 helper + settings 持久化 |
| `services/upgrade_service.py` | 下载逻辑从「多引擎」简化为「只下载 sing-box」；`_handle_plugins`（obfs-local）删除 |
| `scripts/proxy_url_check.sh` | 删除 |

### 协议面

精简后支持：`vmess / vless / trojan / ss / hysteria2 / tuic / direct`。**放弃 ssr / anytls**（sing-box 不支持 SSR，xray 也不支持，无损失）。

## 10. 关键决策与坑

| 坑 | 决策 |
|----|------|
| 订阅刷新不热重载 | 刷新只改 db；运行中的 sing-box 下次重启才重新生成 config（重启粒度：整个 sing-box） |
| 单进程隔离性 | 接受——某协议 bug 崩 sing-box 则全部 service 挂。sing-box 稳定，且容器内可自动重启 |
| current node 单源 | `GET /proxies` 的 `now` 是唯一真相；Python 侧不另存，需要时查询 |
| 重启后节点选择 | `cache_file.enabled: true` 持久化 selector 选择 |
| tag 全局唯一 | 前缀 `n/g/i` + id |
| stop 语义 | `direct`（直连）vs `block`（丢弃）——**待确认** |

## 11. 实施顺序

| 阶段 | 内容 | 前置 |
|------|------|------|
| 0 | **PoC**：手写一份 sing-box config + 真实节点（vmess+vless Reality、ss+obfs），验证 `/delay` 与 `PUT /proxies` 稳定 | 无 |
| 1 | 新分支 `singbox-rewrite`，冻结 db/utils 复用资产 | PoC 通过 |
| 2 | config 生成器（db 模型 → config.json，含 tag 约定） | 1 |
| 3 | 单进程管理（start/stop/restart） | 2 |
| 4 | checker 改造（tcp_check 复用 + clash_api url check） | 3 |
| 5 | 调度层（failover/fallback = selector 切换） | 4 |
| 6 | routes + 前端重写 | 5 |
| 7 | 订阅解析精简 + 下沉 utils + URI 扩展 | 独立，可并行 |

## 12. 验证清单

```bash
# 1. config 生成：db 任意节点组合 → config.json，tag 正确（n/g/i + id）
# 2. 单进程：start/stop/restart 正常，进程组清理干净
# 3. 测速：tcp_check 预筛 + /delay 返回真实延迟；死节点正确标记
# 4. 切换：PUT /proxies/{g} 切节点，毫秒级生效；GET /proxies 读到 now
# 5. failover：节点挂 → 自动切下一健康节点
# 6. fallback：候选全挂 → 切 fallback
# 7. 重启持久化：重启 sing-box 后 selector 保持上次选择（cache_file）
# 8. 订阅刷新：只改 db，不影响运行中的 sing-box；重启后新节点生效
```
