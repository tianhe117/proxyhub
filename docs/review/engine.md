# engine 模块代码评审

对 `app/engine/` 的完整评审（`__init__` / `service` / `xray` / `sslocal` / `singbox`，5 个文件）。

按严重程度分级：**P1** 活跃 bug，**P2** 结构/一致性，**P3** 低优先/可接受。
每条末尾标注**处理决定**（「已定待改」= 方向已确认；「待拍板」= 需要用户决定方向）。

---

## P1 — 活跃 bug

### 1. SSR 节点字段不匹配：加密方式 + 混淆参数全丢

parser 与 engine 对 `ssr` 的字段名对不上，SSR 节点会**静默丢失加密方式**：

**parser**（`subscription_service.py:408-418` `_parse_clash_ssr`）存：

```python
config = {
    'cipher':         p.get('cipher', 'aes-256-cfb'),   # ← 存 cipher
    'password':       p.get('password', ''),
    'obfs':           p.get('obfs', 'plain'),
    'protocol':       p.get('protocol', 'origin'),
    'obfs_param':     p.get('obfs-param', ''),
    'protocol_param': p.get('protocol-param', ''),
}
```

**engine**（`xray.py:87-98` ss/ssr 分支）读：

```python
elif protocol in ('ss', 'ssr'):
    return {'protocol': 'shadowsocks', 'settings': {'servers': [{
        'address': address, 'port': port,
        'method': cfg.get('method', 'aes-256-gcm'),   # ← 读 method，ssr 存的是 cipher
        'password': cfg.get('password', ''),
    }]}}
```

两个问题：

1. **method vs cipher**：ssr 存 `cipher`，engine 读 `method` → 永远落到默认 `aes-256-gcm`，实际加密方式（如 `aes-256-cfb`）丢失。
2. **obfs/protocol 完全忽略**：ssr 特有的 `obfs` / `protocol` / `obfs_param` / `protocol_param` 未被读取，生成的 shadowsocks 配置不含任何混淆。

（对比：`ss` 分支正常，因为 parser 对 ss 存的就是 `method`。）

**根因**：xray 的 `shadowsocks` 协议**表达不了 SSR**（SSR 的 protocol/obfs 是 shadowsocksr 特有，xray 的 shadowsocks 出站不支持）。所以 `PROTOCOL_BIN_MAP['ssr'] = 'xray'` 这个映射本身就是架构问题——SSR 要么走专用 ssr 客户端，要么 parser 就不该产出 ssr 节点。

> **处理：待拍板。** 两个方向：
> - **A. 修字段名 + 补 obfs 映射**：xray ssr 分支读 `cipher` 并尽力映射 obfs（但 xray shadowsocks 协议仍无法完整表达 SSR，只能近似）
> - **B. 承认 SSR 不可用**：从 `PROTOCOL_BIN_MAP` 移除 `ssr`（或标记不支持），parser 不再产出 ssr 节点（或产出时告警）

---

## P2 — 死分支 / 一致性

### 2. `singbox.py:25` — `hysteria`/`hy2` 映射是死分支

```python
if protocol in ('hysteria2', 'hy2', 'hysteria'):
    sing_type = 'hysteria2'
```

parser `_parse_clash_hysteria`（`subscription_service.py:497`）**永远产出 `'protocol': 'hysteria2'`**，从不产出 `hy2` 或 `hysteria`。两个别名分支永不命中。

> **处理：不改（防御性）。** 保留别名无害。

### 3. `build_xray_inbound` 未在 `__init__` 导出

`engine/__init__.py` 只导出 `build_outbound_config`，但 `build_xray_inbound`（xray.py:171）有 2 处调用方都用 `from app.engine.xray import build_xray_inbound`，绕过了包级导出。

> **处理：已改。** `__init__` 补导出 `build_xray_inbound`，调用方（config_service / service_manager）统一走包级。

---

## P3 — 低优先 / 可接受

### 4. `engine/service.py:25` — `config_json` 的异常捕获略过度

```python
try:
    cfg = node['config_json']
except (KeyError, TypeError):
    cfg = {}
```

`except TypeError` 防 `node` 非 dict。调用方都传真实 dict，属防御性代码。**接受不改。**

### 5. vmess `alterId` 类型 —— 无问题

`xray.py:54` `int(cfg.get('alterId', 0))` 已 int 兜底，parser 给字符串也安全。**无问题。**

---

## 处理汇总

| # | 级别 | 决定 |
|---|---|---|
| 1 | P1 | 待拍板：SSR 走「近似修复」还是「标记不支持」 |
| 2 | P2 | 不改（防御性） |
| 3 | P2 | 已改：build_xray_inbound 导出统一 |
| 4 | P3 | 接受不改 |
| 5 | — | 无问题 |

核心是 **#1 SSR**——它决定「SSR 节点到底要不要支持、怎么支持」，是建模层面的决策，不是单纯的字段改名。
