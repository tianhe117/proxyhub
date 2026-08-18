# singbox 模块设计（引擎层）

> 层级：引擎层。本文是 `app/singbox/` 包的设计稿，承接[顶层设计](design.md)核心决策与 [`settings.md`](settings.md) 的单引擎常量/路径布局。
> 状态：⏳ 先方案，确认后再编码。

## 1. 定位

`app/singbox/` 是「跟 sing-box 打交道」的引擎包，覆盖 v2 单一 sing-box 常驻进程的全部运行时与部署职责。包内四个模块：

| 模块 | 职责 | 本文状态 |
|------|------|---------|
| `config.py` | db → `config.json`（纯函数，好单测） | ✅ 本文设计 |
| `process.py` | 单常驻进程 start/stop/restart（无热重载） | ✅ 本文设计 |
| `upgrade.py` | 下载/升级 sing-box 二进制（只下 sing-box） | ✅ 本文设计 |
| `client.py` | clash_api client（`/delay`、GET/PUT `/proxies`） | ⏳ 另立文档（健康检查/调度层） |

模块边界与依赖方向：

```text
app/services（订阅/升级/节点/出站业务）
        │  调 build_config + write_config
        ▼
config.py（纯函数，不依赖 process/client）
        │  产出 data/config.json
        ▼
process.py（读 CONFIG_PATH，启停常驻进程）
        │
        ▼
sing-box 常驻进程 ──clash_api(127.0.0.1:9090)──▶ client.py（调度/健康检查层消费）

upgrade.py（下载二进制 → data/bin/，与 process/config 无运行时耦合）
```

- `config.py` 是纯函数，只依赖 db 行与 settings 常量；`process.py` 只依赖 settings 路径；`upgrade.py` 只依赖 settings 的 `SINGBOX_REPO` / `SINGBOX_ASSET_PATTERNS`。
- 日志统一走 `from app.utils import log`（`log.info(msg)` / `log.error(msg)` / `log.warning(msg)`）。

## 2. 复用 / 改写边界（对应 refer.md §9）

| v1 来源 | 处置 | 落点 |
|---------|------|------|
| `engine/singbox.py`（hysteria2/tuic 出站 dict、字段命名差异） | ✅ 复用核心映射，**扩全 7 协议** | `config.py` |
| `services/config_service.py`（db→config 装配）+ `engine/service.py`（派发） | ♻️ 重写为「单一 config.json + selector 模型」 | `config.py` |
| `engine/xray.py` / `sslocal.py` | ❌ 删（三引擎 → 单引擎） | — |
| `process/manager.py`（`_is_running` / `_kill_pid` / `get_version` / `_scan_processes`） | ✅ 复用底层 helper，**砍多进程/多服务角色** | `process.py` |
| `services/upgrade_service.py`（GitHub API + 解压） | ✅ 复用流程，**砍三引擎泛化 + obfs-local 插件** | `upgrade.py` |
| `PROTOCOL_BIN_MAP` / `BIN_REGISTRY` / `BIN_REPOS`（三引擎） | ❌ 删 → settings 单引擎常量（已就位） | `settings.py` |
| `utils/logger.py` 的 `log(level, module, msg)` 函数式签名 | ♻️ 改 → `log.info(msg)` / `log.error(msg)`，`module` 字段由 `%(funcName)s` 取代 | `utils` |

**日志适配**：v1 调用 `log('info', 'upgrade', ...)`、`log('ok', ...)`、`log('warn', ...)`；v2 全部改为 `log.info(...)` / `log.warning(...)`，`'ok'`→`info`、`'warn'`→`warning`，`module` 参数删除（v2 用 `funcName` 记调用方）。

## 3. config.py — db → config.json

### 3.1 对外接口

```python
def build_config(db_state: dict) -> dict:
    """db 状态 → sing-box config.json 内容（纯函数，无 IO，好单测）。"""

def write_config(config: dict) -> str:
    """config dict 原子写入 settings.CONFIG_PATH，返回路径（唯一 IO）。"""
```

- `build_config` 保持**纯函数**：不读盘、不 import process/client，输入 `db_state`、输出可 JSON 序列化的 dict。
- `db_state` 形如（由调用方从 `app.db.*` 组装，db 层已复用）：

```python
db_state = {
    'nodes':          [node 行],          # id, protocol, address, port, config_json, ...
    'inbounds':       [inbound 行],        # id, protocol, listen_addr, port, params_json
    'outbounds':      [outbound 行],       # id, name（id=0 为 direct 哨兵）
    'outbound_nodes': [pool 条目],         # outbound_id, node_id, priority
    'services':       [service 行],        # id, name, inbound_id, outbound_id
}
```

- `node.bin_type` 字段 v2 已无意义（单一 sing-box），db 层保留不动，`config.py` 忽略之。

### 3.2 tag 约定

| tag | 含义 | 示例 |
|-----|------|------|
| `i{id}` | 用户入站（inbound id） | `i3` |
| `g{id}` | selector 组（outbound id） | `g5` |
| `n{id}` | 真实节点出站（node id） | `n12` |
| `direct` / `block` | 静态保留出站 | `direct` / `block` |

### 3.3 config.json 顶层结构

```json
{
  "log": {"level": "info", "timestamp": true},
  "inbounds": [
    { "type": "http", "tag": "i1", "listen": "0.0.0.0", "listen_port": 8081, "users": [...] }
  ],
  "outbounds": [
    { "type": "vmess",  "tag": "n12", "server": "...", "server_port": 443, "uuid": "..." },
    { "type": "selector", "tag": "g5", "outbounds": ["n12", "n13", "direct"] },
    { "type": "direct", "tag": "direct" },
    { "type": "block",  "tag": "block" }
  ],
  "route": {
    "rules": [ { "inbound": ["i1"], "outbound": "g5" } ],
    "final": "direct"
  },
  "experimental": {
    "clash_api": { "external_controller": "127.0.0.1:9090", "secret": "" }
  }
}
```

> 修正：clash_api **不是独立入站**，而是 sing-box 的 `experimental.clash_api` 块（`external_controller` 指定监听地址）。selector/出站会自动暴露为 clash API 的 proxy group / proxy，无需额外入站 tag。

组装顺序（`build_config` 内部）：

1. **节点出站**：遍历 `nodes`，每个真实节点生成 `n{id}` 出站（§3.5）。
2. **selector 组**：遍历 `outbounds`（id>0），每个生成 `g{id}` selector（§3.6）。
3. **用户入站**：遍历 `inbounds`，每个生成 `i{id}` 入站（§3.4）。
4. **静态出站**：追加 `direct`、`block`。
5. **route**：遍历 `services`，每条生成 `{inbound: [i{inbound_id}], outbound: ...}` 规则（§3.7）；`final` 固定 `direct`。

### 3.4 入站生成（inbound → i{id}）

`inbound.protocol` ∈ `VALID_INBOUND_PROTOCOLS`(`http/socks/ss/vmess`)，参数在 `params_json`。

| protocol | sing-box `type` | 关键字段 |
|----------|----------------|---------|
| `http` | `http` | `users: [{username, password}]`（可空） |
| `socks` | `socks` | `users: [{username, password}]`（可空） |
| `ss` | `shadowsocks` | `method`、`password` |
| `vmess` | `vmess` | `users: [{uuid, alterId}]` |

通用字段：`tag = i{id}`、`listen = listen_addr`（默认 `0.0.0.0`）、`listen_port = port`。

```python
# http / socks 示例
{"type": "http", "tag": "i1", "listen": "0.0.0.0", "listen_port": 8081,
 "users": [{"username": params.get('username', ''), "password": params.get('password', '')}]}
```

### 3.5 节点出站生成（node → n{id}，协议面）

`node.protocol` ∈ `SUPPORTED_PROTOCOLS`(`vmess/vless/trojan/ss/hysteria2/tuic/direct`)。协议参数在 `node.config_json`（JSON 字符串，解析为 flat dict）。sing-box 字段命名差异（承自 `engine/singbox.py`）：`type`（非 `protocol`）、`server`+`server_port`（非 `address`/`port`）、`tls.server_name`（非 `serverName`）、`tls.insecure`（非 `allowInsecure`）。

| node.protocol | sing-box `type` | config_json 关键键 → sing-box 字段 |
|---------------|----------------|-----------------------------------|
| `vmess` | `vmess` | `uuid`/`id`→`uuid`，`alterId`→`alter_id`，`security`→`security`，`network`/`tls`/传输键 → 见下 |
| `vless` | `vless` | `uuid`/`id`→`uuid`，`flow`→`flow`，`encryption`→`encryption` |
| `trojan` | `trojan` | `password`→`password` |
| `ss` | `shadowsocks` | `method`→`method`，`password`→`password`（`plugin`/`plugin_opts` 删，v2 无 obfs） |
| `hysteria2` | `hysteria2` | `password`/`sni`/`alpn`/`up_mbps`/`down_mbps`/`obfs`/`obfs_password`（承 `engine/singbox.py`） |
| `tuic` | `tuic` | `uuid`/`password`/`sni`/`alpn`/`congestion_control`/`udp_relay_mode`（承 `engine/singbox.py`） |
| `direct` | `direct` | 无（直连出站，无 server） |

通用字段：`tag = n{id}`、`server = address`、`server_port = int(port)`。

**TLS / 传输公共块**（vmess/vless/trojan 共用，`cfg.get('tls')` 为真才生成）：

```python
# TLS
{"tls": {"enabled": True,
         "server_name": cfg.get('sni', ''),
         "insecure": bool(cfg.get('allowInsecure')),
         "alpn": cfg['alpn'].split(',') if isinstance(cfg.get('alpn'), str) else cfg.get('alpn'),
         # fingerprint 可选 → tls.utls
        }}

# 传输（network ∈ tcp/ws/h2/grpc，映射到 sing-box transport）
#   ws  → {"type":"ws","path":cfg['ws_path'],"headers":{"Host":cfg['ws_host']}}
#   h2  → {"type":"http","host":...,"path":cfg['h2_path']}
#   grpc→ {"type":"grpc","service_name":cfg['grpc_service_name']}
#   tcp → 无 transport 块
```

> 传输块的精确 sing-box 字段（`transport` vs 旧 `network` 键）在实现时按目标 sing-box 版本定稿；设计锚点是「network + 各传输参数」这一组 config_json 键必须全部落进 outbound。

hysteria2 / tuic 出站 dict 直接沿用 `engine/singbox.py` 的 `_build_outbound`（已含 `tls.server_name` / `tls.insecure` 的 v2 命名），仅补 `tag = n{id}`。

### 3.6 selector 组生成（outbound → g{id}）

每个 `outbound`（`id > 0`）对应一个 selector：

```python
pool_node_ids = [e['node_id'] for e in outbound_nodes if e['outbound_id'] == oid]  # 按 priority ASC
{"type": "selector", "tag": f"g{oid}",
 "outbounds": [f"n{nid}" for nid in pool_node_ids] + ["direct"]}
```

- 顺序即优先级：**`pool[0]`（priority 最小）排最前 = 默认选中节点**，契合 design.md §4「重启后 selector 直接用 default 节点」。
- 末尾追加 `direct` 作为保底（全节点失效时不至于断网）；是否需要 `block` 由后续定，当前 `direct` 兜底。
- `id=0`（direct 哨兵）不生成 selector，route 直接指 `direct`。
- selector 的「当前选中」由调度层经 clash_api `PUT /proxies/{g}` 切换，`config.py` 不参与。

### 3.7 route 生成

每条 `service`（`inbound_id` → `outbound_id`）生成一条规则：

```python
outbound = f"g{outbound_id}" if outbound_id > 0 else "direct"
{"inbound": [f"i{inbound_id}"], "outbound": outbound}
```

`route.final = "direct"`（未命中任何入站时直连）。`outbound_fallback`（快速切换节点）是调度层概念，`config.py` 不消费。

### 3.8 错误处理

- `node.protocol` 不在 `SUPPORTED_PROTOCOLS` → `ValueError`（协议面非法，属数据错误，向上抛）。
- 悬挂引用（service 指向不存在的 inbound/outbound、pool 指向已删 node）→ 跳过该条并 `log.warning`（不让单条坏数据炸掉整个 config）。
- `write_config` 复用 settings 的原子写模式（tmp + `os.replace`）。

## 4. process.py — 单常驻进程管理

### 4.1 对外接口

```python
def start() -> int:            # 启动常驻进程，返回 pid；已运行则返回现有 pid（幂等）
def stop() -> dict:            # 停止常驻进程，返回 {success, message, killed}
def restart() -> dict:         # stop + start，返回 {success, message}
def is_running() -> bool:      # 常驻进程是否存活
def get_version() -> str:      # sing-box 版本串，拿不到返回 'N/A'
```

- 无热重载：`restart()` = 先停后起。任何配置变更后由调用方 `write_config(...)` + `restart()`。

### 4.2 进程识别（无 PID 文件，Docker 原生）

沿用 `manager.py` 的「直接扫系统进程」策略（单一进程更简单）：

```python
def _find_pid() -> int | None:
    """ps -eo pid,stat,comm,args 扫一遍，找 sing-box 常驻进程。

    匹配：comm == 'sing-box' 且 args 含 CONFIG_PATH 的 basename（config.json）。
    排除僵尸（stat 含 'Z'）与自身。"""
```

- 启动时 `Popen` 返回的 pid 同时存模块级 `_pid`，`is_running()` / `stop()` 优先用 `_pid`，失效再扫。
- 单一常驻进程最多一个，`_find_pid` 命中即返回。

### 4.3 启停策略

```python
def start():
    bin_path = settings.SINGBOX_BIN_PATH        # 已是绝对路径常量
    if not os.path.isfile(bin_path): raise RuntimeError(f'Binary not found: {bin_path}')
    if is_running(): return _pid                 # 幂等
    cmd = [bin_path] + [a.format(config=settings.CONFIG_PATH)
                        for a in settings.SINGBOX_RUN_ARGS]
    proc = subprocess.Popen(cmd, stdout=DEVNULL, stderr=DEVNULL, preexec_fn=os.setsid)
    time.sleep(0.2)
    if proc.poll() is not None: raise RuntimeError(f'sing-box exited immediately: {proc.returncode}')
    return proc.pid
```

- `preexec_fn=os.setsid`：每个进程独立会话，为 `stop()` 按进程组杀提供前提（承 `manager.py`）。
- 无 `stdout/stderr` 重定向到日志文件（日志走 `app.utils` 的 `log`，进程输出丢弃）。

```python
def _kill_pid(pid, timeout=3):   # 承 manager.py：SIGTERM → 轮询 → SIGKILL
    pgid = os.getpgid(pid); os.killpg(pgid, signal.SIGTERM)
    for _ in range(int(timeout / 0.3)):
        if not _is_running(pid): return True
        time.sleep(0.3)
    os.killpg(pgid, signal.SIGKILL)
    return not _is_running(pid)
```

- `_is_running(pid)` 复用 `manager.py` 的 `/proc/{pid}/stat` 状态判断（区分僵尸/死进程）。
- `stop()`：`_find_pid()` 无果 → 返回 `{'success': True, 'message': 'No process', 'killed': 0}`；有则 `_kill_pid`。
- `get_version()`：`subprocess.run([bin_path] + SINGBOX_VERSION_ARGS)`，取第一行非空输出。

### 4.4 关键决策

| 决策 | 内容 | 理由 |
|------|------|------|
| 无 PID 文件 | 进程识别靠扫进程 + 内存 `_pid` | 承 manager.py 的 Docker 原生思路，避免 PID 文件漂移/残留 |
| 进程组杀 | `setsid` + `killpg` SIGTERM→SIGKILL | 顺带收掉 sing-box 可能起的子进程 |
| 幂等 start | 已运行则返回现有 pid | 单常驻进程，重复 start 是调用方常见场景 |
| 只存内存 pid | 不落盘 | 单一进程、无跨重启状态（design.md §4 明确不跨重启保留） |

## 5. upgrade.py — 下载 / 升级

### 5.1 对外接口

```python
def check_upgrade() -> dict:     # 查 GitHub 最新 release
    # {success, current_version, latest_version, download_url, asset_name, is_update}

def download_upgrade() -> dict:  # 下载 + 整包解压 + 落 data/bin/（含 libcronet.so）
    # {success, message, version}
```

- 只下 sing-box：仓库/资产模式取 `settings.SINGBOX_REPO` / `settings.SINGBOX_ASSET_PATTERNS`，无三引擎泛化、无 obfs-local 插件（v2 已删）。

### 5.2 流程（承 `upgrade_service.py`，砍泛化）

```python
def check_upgrade():
    current_raw = process.get_version()                 # 复用 process.py
    current = re.search(r'(\d+\.\d+\.\d+)', current_raw)  # "sing-box version 1.13.13" → 1.13.13
    # GitHub API: https://api.github.com/repos/SagerNet/sing-box/releases/latest
    #   Accept: application/vnd.github.v3+json, User-Agent: ProxyHub/1.0, timeout=15
    latest = release['tag_name'].lstrip('v')
    # 资产匹配：SINGBOX_ASSET_PATTERNS['linux-64'] = ['linux-amd64', 'linux-x64']
    #   对 release['assets'] 逐个 name 匹配子串 → 得 download_url / asset_name
    return {..., 'is_update': current != latest}

def download_upgrade():
    check = check_upgrade()
    if not check['success'] or not check['is_update']: return ...
    # urllib 下载（timeout=120）→ NamedTemporaryFile
    # 整包解压到 settings.SINGBOX_BIN_DIR：
    #   .tar.gz/.tgz → tarfile 'r:gz'，.tar.xz → 'r:xz'，.zip → zipfile，裸二进制 → 直写
    #   strip 顶层版本目录，全部成员平铺到 bin/（sing-box + libcronet.so 等）
    #   保留 tar 成员权限（sing-box 可执行）
```

- 内部 helper：`_extract_tar` / `_extract_zip`（承 `upgrade_service.py`，删 `_handle_plugins`）。
- 升级后由调用方决定是否 `process.restart()`（`upgrade.py` 本身不启停进程）。

### 5.3 关键决策

| 决策 | 内容 | 理由 |
|------|------|------|
| 只下 sing-box | 常量化 repo/资产，删 `BIN_REPOS` 字典与 `bin_name` 参数 | 单引擎，无选择面 |
| 删插件 | 无 `_handle_plugins` | v2 无 obfs-local（design.md 核心决策 1） |
| 版本取 process | `check_upgrade` 复用 `process.get_version()` | 避免重复实现版本读取 |
| 升级不自动重启 | 只落二进制，启停交给调用方 | 职责单一，进程生命周期归 process.py |

## 6. 与 v1 差异速览

| 项 | v1 | v2 |
|----|----|----|
| 引擎 | xray + sslocal + sing-box 三套 | 单一 sing-box |
| 配置 | 每 service 一个 config 目录（`xray_in.json` / `{bin}_out.json`） | 单一 `data/config.json`（selector 模型） |
| 进程 | 每 service 一对 in/out 进程 | 单常驻进程 start/stop/restart |
| 节点 → 出站 | `build_outbound_config(node, local_port)` + SOCKS5 中间跳 | `n{id}` 直接出站，无中间 SOCKS5 端口 |
| 切换 | 改 config + 重启进程对 | clash_api `PUT /proxies/{g}`（client.py，另立） |
| 升级 | 三引擎泛化 + obfs 插件 | 只 sing-box，无插件 |
| 日志 | `log('info', module, msg)` | `log.info(msg)`（`funcName` 取代 module） |

## 7. 边界与后续

- **client.py 另立文档**：clash_api client（`get_delay` / `get_proxies` / `select_proxy`）是健康检查层与调度层的公共叶子，随这两层细化时一并设计。
- **db 层未落地**：当前分支 `app/db/` 仅占位，`build_config` 的输入 `db_state` 由服务层从 `app.db.*`（复用 v1 模型）组装；db 层移植不在本文范围。
- **默认兜底**：selector 末尾固定追加 `direct`；若后续要「全失效则断网」语义，改用 `block`（一行差异）。
- **transport 字段**：vmess/vless 的传输块（ws/http/grpc）精确 sing-box 字段按目标版本在实现时定稿。
- 对应 [`refer.md` §9 复用清单](refer.md) 的 engine / process / upgrade 三块，本文是它们的单引擎收敛方案。
