# 订阅解析模块设计（parser）

> Archive: historical design document; not the current implementation status.

> 层级：工具层 / 业务层。本文是 `app/parser/`（解析）+ `app/services/subscription.py`（业务）的设计稿。
> 状态：⏳ 先方案，确认后再编码。

## 1. 定位

订阅解析分两层：

| 层 | 模块 | 职责 | 依赖 |
|----|------|------|------|
| 解析层 | `app/parser/` | URI 文本 → 节点 dict 列表（纯函数，好单测） | 零（只用 stdlib） |
| 业务层 | `app/services/subscription.py` | 拉取 URL → 调解析层 → 对比 DB → 增删改 | `app.parser` + `app.db` + `urllib` |

```
订阅 URL
    │  HTTP GET
    ▼
services/subscription.py ─── urllib 拉取
    │
    │  base64 decode + keyword 过滤
    ▼
parser/__init__.py ─── parse_all()
    │  按 URI 前缀分发
    ├─▶ parser/ss.py        ss://...
    ├─▶ parser/vmess.py     vmess://...
    ├─▶ parser/vless.py     vless://...
    ├─▶ parser/trojan.py    trojan://...
    ├─▶ parser/hysteria2.py hy2://...
    └─▶ parser/tuic.py      tuic://...
    │
    │  返回 list[dict]
    ▼
services/subscription.py ─── sync_nodes()
    │  按 name 做 diff
    ▼
app/db/node.py ─── 增删改写入 DB
```

## 2. 解析层 — `app/parser/`

### 2.1 统一输出格式

每个协议的 `parse()` 返回相同结构：

```python
{
    'name':        '节点名称',        # URI #fragment 或解析出的标识
    'protocol':    'ss',             # ss / vmess / vless / trojan / hysteria2 / tuic
    'address':     'example.com',    # 服务器地址
    'port':        443,              # 服务器端口（int）
    'config_json': '{"method":...}'  # 协议特定参数（JSON str）
}
```

`config_json` 内部 key 与 DB `nodes.config_json` 一致，可直接写入。

### 2.2 URI 格式参考

| 协议 | URI 格式 | 示例 |
|------|---------|------|
| ss | `ss://base64(method:password)@host:port#name` | `ss://YWVzLTI1Ni1nY206cHc=@1.2.3.4:8388#节点1` |
| vmess | `vmess://base64(json)` | `vmess://eyJhZGQiOiIxLjIuMy40IiwicG9ydCI6NDQzLC...` |
| vless | `vless://uuid@host:port?params#name` | `vless://abc-uuid@1.2.3.4:443?tls=true&sni=x.com#节点` |
| trojan | `trojan://password@host:port?params#name` | `trojan://pw@1.2.3.4:443?sni=x.com#节点` |
| hysteria2 | `hy2://password@host:port?params#name` | `hy2://pw@1.2.3.4:443?sni=x.com#节点` |
| tuic | `tuic://uuid:password@host:port?params#name` | `tuic://uuid:pw@1.2.3.4:443?congestion=bbr#节点` |

### 2.3 模块结构

```
app/parser/
├── __init__.py      ← parse_all() 统一入口
├── base.py          ← decode_base64, filter_lines, parse_uri
├── ss.py            ← ss:// URI → dict
├── vmess.py         ← vmess:// URI → dict
├── vless.py         ← vless:// URI → dict
├── trojan.py        ← trojan:// URI → dict
├── hysteria2.py     ← hy2:// URI → dict
└── tuic.py          ← tuic:// URI → dict
```

### 2.4 对外接口

```python
# app/parser/__init__.py
def parse_all(raw_text: str, include: str = '', exclude: str = '') -> list[dict]:
    """订阅原文 → 解析后的节点列表。

    流程：base64 decode → 按行拆分 → 按前缀分发解析 → keyword 过滤 → 返回。
    单条解析失败跳过，不影响其他节点。
    """
```

```python
# app/parser/base.py
def decode_base64(text: str) -> str:
    """URL-safe base64 decode，容错处理。"""

def filter_lines(lines: list[str], include: str, exclude: str) -> list[str]:
    """按 include/exclude 关键词过滤 URI 行。"""

def parse_kv_params(query: str) -> dict:
    """解析 URL query string → dict（?key1=val1&key2=val2）。"""
```

### 2.5 关键设计点

| 点 | 方案 |
|----|------|
| 错误容忍 | 单条 `parse()` 异常 → `log.warning` + 跳过，不中断 |
| 重复节点 | 按 `name` 去重，后者覆盖前者 |
| 未知协议 | 跳过 + `log.warning`，不抛异常 |
| base64 容错 | 先试 URL-safe decode，失败试标准 decode，再失败跳过 |
| keyword 过滤 | include：任一关键词命中即保留；exclude：任一命中即排除 |

### 2.6 新增协议流程

1. 在 `app/parser/` 新建 `{protocol}.py`，实现 `parse(uri) → dict`
2. 在 `app/parser/__init__.py` 的分发逻辑加一个 `elif`
3. `app/settings.py` 的 `SUPPORTED_PROTOCOLS` 加协议名
4. 完成

## 3. 业务层 — `app/services/subscription.py`

### 3.1 对外接口

```python
def fetch_and_parse(url: str, include: str = '', exclude: str = '') -> list[dict]:
    """拉取订阅 URL → 解析 → 返回节点列表。

    HTTP GET（timeout=15）→ base64 decode → parse_all。
    也会尝试从响应头 Subscription-Userinfo 提取流量信息。
    """

def sync_nodes(sub_id: int, url: str, include: str = '', exclude: str = '') -> dict:
    """拉取 + 解析 + 对比 DB + 增删改。

    Returns: {added: N, updated: N, removed: N, total: N, traffic: {...}}
    """

def refresh_subscription(sub_id: int) -> dict:
    """完整刷新单个订阅：读 DB 获取 url/filter → sync_nodes → 更新 updated_at。

    Returns: {success, message, added, updated, removed, total}
    """
```

### 3.2 sync_nodes 内部流程

```python
def sync_nodes(sub_id, url, include, exclude):
    # 1. 拉取 & 解析
    new_nodes = fetch_and_parse(url, include, exclude)

    # 2. 调用 db.subscription.sync_nodes（已有 name diff 逻辑）
    result = db.subscription.sync_nodes(sub_id, new_nodes)

    # 3. 返回统计
    return {
        'added':   result['inserted'],
        'updated': result['updated'],
        'removed': result['deleted'],
        'total':   len(new_nodes),
    }
```

> `db.subscription.sync_nodes` 已实现 name-based diff + 增删改，直接复用。

### 3.3 流量信息解析

部分订阅服务在 HTTP 响应头中返回流量信息：

```
Subscription-Userinfo: upload=123; download=456; total=789; expire=1234567890
```

在 `fetch_and_parse` 中解析此头，返回给调用方，由 `refresh_subscription` 写入 DB：

```python
def _parse_userinfo(header_value: str) -> dict:
    """Parse Subscription-Userinfo header → {upload, download, total, expire}."""
```

### 3.4 依赖方向

```
services/subscription.py
    ├── app.parser        （解析）
    ├── app.db.subscription  （DB 读写）
    ├── app.db.node          （DB 读写）
    └── urllib.request     （HTTP 拉取）
```

不依赖 `app.singbox`（配置生成/进程管理）。

## 4. 与现有代码的对接

| 现有代码 | 作用 | 对接方式 |
|---------|------|---------|
| `db.subscription.sync_nodes()` | name-based diff + 增删改 | 直接复用，parser 输出格式与其入参一致 |
| `db.subscription.update()` | 更新 updated_at / 流量字段 | refresh_subscription 调用 |
| `settings.SUPPORTED_PROTOCOLS` | 协议白名单 | parser 用于验证 |
| `utils.logger.log` | 日志 | parser 异常记录 |

## 5. 错误处理

| 场景 | 处理 |
|------|------|
| HTTP 请求失败 | `fetch_and_parse` 抛异常，`refresh_subscription` 捕获返回 `{success: False}` |
| base64 decode 失败 | 跳过整段文本，`log.warning` |
| 单条 URI 解析失败 | 跳过该条，`log.warning`，继续解析其他 |
| 未知协议前缀 | 跳过，`log.warning` |
| DB 写入失败 | `sync_nodes` 内部 rollback，向上抛异常 |
| keyword 过滤后为空 | 返回空列表，正常流程 |

## 6. 测试策略

| 层 | 测试方式 |
|----|---------|
| parser | 纯函数单测：每种协议准备 2-3 个真实 URI，验证解析结果 |
| base | 单测：base64 容错、keyword 过滤边界 |
| services | 集成测试：mock HTTP 响应 → 调 sync_nodes → 检查 DB |
