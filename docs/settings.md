# settings.py 设计（单引擎版）

> 层级：数据层 / 配置持久化。本文是 `app/settings.py` 的分层细化稿，承接[顶层设计](design.md)核心决策与 [`refer.md` §9 复用清单](refer.md)。
> 状态：⏳ 已按「单一 sing-box」改造，待数据层/Web 层联调校验。

## 1. 定位

settings.py 承担两类职责：

1. **配置持久化**：`setting.json` 读写（`_store` 内存 + 磁盘原子写），供 Web 设置页与各业务层读取。
2. **常量与路径**：单引擎 sing-box 的二进制/仓库常量、支持协议列表、运行时路径 helper。

与 v1 相比：**多引擎字段全部删除**，只保留 sing-box 一份常量；路径从「仓库内 bin/config」改为「`data/` + `logs/`」布局，并支持 `PROXYHUB_HOME` 环境变量覆盖。

## 2. 复用 / 改写边界（对应 refer.md §9）

| 项 | 处置 |
|----|------|
| `_store` + `setting.json` 持久化机制（`_load_from_disk`/`_persist_to_disk`/`get_setting`/`set_setting`/`update_settings`/`reset_to_defaults`） | ✅ 保留，原样复用 |
| `BIN_REGISTRY`（三引擎） | ❌ 删除 → 单引擎常量 `SINGBOX_EXE` / `SINGBOX_RUN_ARGS` / `SINGBOX_VERSION_ARGS` |
| `BIN_REPOS`（含 obfs-local） | ❌ 删除 → `SINGBOX_REPO` / `SINGBOX_ASSET_PATTERNS`（只下 sing-box） |
| `PROTOCOL_BIN_MAP` | ❌ 删除 → `SUPPORTED_PROTOCOLS` 协议列表（单引擎无需映射） |
| `SOCKS_PORT_*` / `TEST_PORT_*` 端口池 | ❌ 删除（单一进程无中间 Socks5 跳、无 test 端口池；端口占用探测保留在 `utils/port.py` 的 `is_port_available`） |
| `config_dir` 设置项 | ❌ 删除 → 生成配置固定落 `data/config.json` |
| 路径 helper | ✅ 改后复用：`data/` `logs/` `bin` `config.json` 布局 + `PROXYHUB_HOME` 覆盖 |

## 3. DEFAULT_SETTINGS 字段表

| key | 默认值 | 说明 |
|-----|--------|------|
| `bin_path_singbox` | `./data/bin/sing-box` | sing-box 二进制路径（v1 是 `./bin/sing-box`） |
| `check_interval_normal` | `240` | 常规检查间隔（秒） |
| `check_interval_failover` | `30` | failover 检查间隔（秒） |
| `tcp_timeout` | `3` | TCP 直连预筛超时（秒） |
| `curl_timeout` | `5` | clash_api `/delay` 超时（秒），映射该端点的 `timeout` 参数 |
| `test_url` | `https://www.gstatic.com/generate_204` | URL 测速目标 |
| `web_port` | `8080` | Web 监听端口 |
| `web_username` | `admin` | 登录用户名 |
| `web_password` | `` | 登录密码（空=免密） |

> 说明：`curl_timeout` 沿用 v1 命名（内部语义变为 clash_api `/delay` 的 timeout，非 curl 子进程）；`check_*` 间隔继续由调度层消费。

## 4. 单引擎常量

```python
SINGBOX_EXE = 'sing-box'
SINGBOX_VERSION_ARGS = ['version']
SINGBOX_RUN_ARGS = ['run', '-c', '{config}']   # {config} 由进程层替换为 data/config.json
SINGBOX_REPO = 'SagerNet/sing-box'
SINGBOX_ASSET_PATTERNS = {'linux-64': ['linux-amd64', 'linux-x64']}
```

- `SINGBOX_RUN_ARGS` 供 `app/singbox/process.py` 起进程；`{config}` 占位符由调用方替换。
- `SINGBOX_REPO` / `SINGBOX_ASSET_PATTERNS` 供升级服务（`services/upgrade_service.py`）只下载 sing-box。

## 5. 协议面

```python
SUPPORTED_PROTOCOLS = ('vmess', 'vless', 'trojan', 'ss', 'hysteria2', 'tuic', 'direct')
```

- 单引擎无「协议 → bin」映射，仅作为节点/订阅协议校验的合法值集合。
- 放弃 `ssr` / `anytls`（sing-box 不支持 SSR；anytls 未纳入 v2 支持面）。

```python
VALID_INBOUND_PROTOCOLS = ('http', 'socks', 'ss', 'vmess')
```

- sing-box 本地入站协议合法值集合（供配置生成层校验 inbound 类型），与节点协议面 `SUPPORTED_PROTOCOLS` 分离。

## 6. 路径布局（核心决策 4：一套目录两种跑法）

```
BASE_DIR = PROXYHUB_HOME（环境变量） 或 app/ 的上级目录
├── data/
│   ├── bin/sing-box      # get_bin_dir() + SINGBOX_EXE → get_singbox_bin_path()
│   ├── config.json       # get_config_path()：生成的 sing-box 配置
│   ├── setting.json      # get_settings_path()：本模块持久化文件
│   └── proxyhub.db       # get_db_path()：SQLite
└── logs/                 # get_logs_dir()：启动日志（YYYY-MM-DD_HHMMSS.log）
```

- 路径不硬编码：`BASE_DIR` 可被 `PROXYHUB_HOME` 覆盖（Docker volume 挂载 / venv 仓库根）。
- `get_singbox_bin_path()` 返回 `get_setting('bin_path_singbox')`（默认 `data/bin/sing-box`），路径可在 Web 设置页覆盖。
- 无 `config/` 目录、无 `bin/` 顶层目录：v2 全部运行时产物收敛进 `data/`。

## 7. 持久化机制（复用 v1，未改）

- 模块导入时 `_load_from_disk()` 读 `setting.json`；文件缺失或 JSON 损坏则用 `DEFAULT_SETTINGS` 重建并落盘。
- 读走内存 `_store`；写（`set_setting` / `update_settings` / `reset_to_defaults`）先改内存再 `_persist_to_disk` 原子写（tmp 文件 + `os.replace`）。
- `setting.json` 已 gitignore（运行时状态，docker=volume）。

## 8. 与 v1 差异速览

| 字段/常量 | v1 | v2 |
|-----------|----|----|
| `bin_path_xray` / `bin_path_sslocal` | 有 | 删 |
| `bin_path_singbox` 默认 | `./bin/sing-box` | `./data/bin/sing-box` |
| `config_dir` | `./config` | 删（`data/config.json`） |
| `BIN_REGISTRY` / `BIN_REPOS` | 三引擎 | 单引擎常量 |
| `PROTOCOL_BIN_MAP` | 协议→bin | `SUPPORTED_PROTOCOLS` 列表 |
| `SOCKS_PORT_*` / `TEST_PORT_*` | 有 | 删 |
| `get_config_dir()` | 有 | 删 → `get_config_path()` |
