# 订阅服务重构方案

## 背景

`app/services/subscription_service.py` 588 行，职责拧在一起：

| 类别 | 函数 | 副作用 |
|------|------|--------|
| 拉取 | `_fetch_subscription` | 有（网络） |
| 解析 | `_decode_body` / `_parse_content` / `_parse_standard` / `_parse_vmess_link` / `_parse_ss_link` / `_parse_clash_yaml` / `_parse_clash_proxy` + 各协议 parser + `_apply_filters` / `_assign_bin_type` | 无（纯函数） |
| 落库 | `refresh_subscription`（调 sync_nodes / clear_nodes / update） | 有（db） |

同时有两个悬而未决的历史包袱：

1. **协议面过宽**：`PROTOCOL_BIN_MAP` 含 `ssr` / `anytls` / `hysteria`，但引擎跑不了（xray 无 ssr/anytls 分支、sing-box 无 hysteria 产出），形成「能存库、启动报错」的静默失败。
2. **格式命名过时**：parser 还叫 `_parse_clash_*`，但解析的 vless / hysteria2 / tuic / anytls 全是 **Mihomo**（Clash Meta）时代的协议，原 Clash 早已停维。

本方案分三步，每步独立可提交：协议精简 → 分层下沉 → 改名。

---

## 第一步：协议面精简（放弃不支持的协议）

### 目标

`PROTOCOL_BIN_MAP` 收敛到引擎真正能跑的 7 个协议：

```python
PROTOCOL_BIN_MAP = {
    'vmess':     'xray',
    'vless':     'xray',
    'trojan':    'xray',
    'direct':    'xray',
    'ss':        'sslocal',
    'hysteria2': 'sing-box',
    'tuic':      'sing-box',
}
```

### 放弃的协议

| 协议 | 放弃理由 |
|------|----------|
| `ssr` | xray 的 shadowsocks 出站无 `obfs`/`protocol`，物理跑不了（已查证 Xray 官方文档） |
| `anytls` | xray.py `_build_outbound` 无 anytls 分支，engine 必抛 `ValueError` |
| `hysteria`（不带2） | parser 从不产出（只产出 `hysteria2`），死 key |

### 改动清单

| 文件 | 改动 |
|------|------|
| `app/settings.py` | `PROTOCOL_BIN_MAP` 精简为上述 7 项 |
| `app/services/subscription_service.py` | ① `_parse_clash_proxy` 删 `ssr` / `anytls` 两个分支；② 删 `_parse_clash_ssr` / `_parse_clash_anytls` 两个函数；③ 删死代码 `assign_bin_type`（全项目无调用者） |
| `app/engine/xray.py` | `_build_outbound` 的 `protocol in ('ss', 'ssr')` 改 `protocol == 'ss'` |
| `app/db/node.py` | docstring 协议列表删 `ssr / anytls / hysteria` |

前端 `nodes.html` 协议下拉已是 `vmess / vless / trojan / ss / hysteria2 / tuic`，**无需改**。

### 影响

订阅里若含 ssr / anytls 节点，刷新后被**静默跳过**（不产出、不提示）。是否在 `refresh_subscription` 记一条 log（"跳过 N 个不支持的节点"）——见第三步，可选。

---

## 第二步：解析下沉到 utils

### 分层决策

parser 是「外部格式 → 内部 node dict」的**纯函数**，产物 node dict 被 db 存、被 checker 用、被 engine 消费，是跨层共享契约。放 **utils** 最合适：

| 层 | 理由 |
|----|------|
| ✅ utils | 叶子层纯函数，跨层共享，无网络/db 副作用 |
| ❌ engine | 会把「造 node」和「用 node」两个相反职责挤进一层 |
| ❌ services | 应只保留「有副作用」的编排（fetch + sync） |

依赖方向无环：`utils/subscription.py` 依赖 `settings`（读 `PROTOCOL_BIN_MAP`）——这是 `utils/validators.py`、`utils/logger.py` 已有的既有方向。

### 目标结构

```
app/utils/subscription.py      # 纯解析（decode / parse / filter），零副作用
app/services/subscription_service.py  # 只留 _fetch_subscription + refresh_subscription 编排
```

`refresh_subscription` 变成薄编排：`fetch`（自己）→ `parse_content`（调 utils）→ `apply_filters`（调 utils）→ `sync_nodes`（调 db）。

### 搬移明细

从 `services/subscription_service.py` 迁到 `utils/subscription.py`：

- `_decode_body`
- `_parse_content` / `_parse_standard`
- `_parse_vmess_link` / `_vmess_config_to_standard`
- `_parse_ss_link`
- `_parse_clash_yaml` / `_extract_proxies_block` / `_parse_clash_proxy` + 保留的各协议 `_parse_clash_*`
- `_apply_filters`
- `_apply_clash_transport`

services 层保留：

- `_fetch_subscription`（网络）
- `refresh_subscription`（编排，import utils 的解析函数）

### 命名约定

解析函数从私有 `_parse_*` 改为**公开**（`parse_content` / `parse_standard` / `parse_vmess_link` / `parse_yaml` / `apply_filters` …），因为跨层调用，不再是模块内部实现细节。`utils/subscription.py` 顶部 docstring 定义 node dict 契约（字段形状），作为单一来源。

---

## 第三步：URI 协议扩展

### 目标

`parse_standard` 现只支持 `vmess://` / `ss://` 两种 URI scheme，与精简后的协议面（vmess/vless/trojan/ss/hysteria2/tuic）不一致——vless/trojan/hysteria2/tuic 只能靠 YAML 格式进来，纯 URI 订阅会漏掉整类协议。

补上四个 URI scheme，每个协议一个独立 parser，与协议面保持一致：

| URI scheme | parser 函数 | bin_type |
|------------|-------------|----------|
| `vmess://` | `parse_vmess_link`（已有） | xray |
| `ss://` | `parse_ss_link`（已有） | sslocal |
| `vless://` | `parse_vless_link`（新增） | xray |
| `trojan://` | `parse_trojan_link`（新增） | xray |
| `hysteria2://` | `parse_hysteria2_link`（新增） | sing-box |
| `tuic://` | `parse_tuic_link`（新增） | sing-box |

> `direct` 无 URI scheme，是合成节点，不在扩展范围。

### 改动清单

| 文件 | 改动 |
|------|------|
| `app/utils/subscription.py` | `parse_standard` 增加 vless/trojan/hysteria2/tuic 四个 scheme 分派 + 四个新 parser 函数 |

字段复用现有 YAML parser 的配置字段名（`uuid`/`sni`/`flow`/`congestion_control` 等），保证 engine 侧消费的 node dict 契约一致。

---

## 第四步：通用命名 + 跳过告警

### 命名

接口名**不带 clash / mihomo 前缀**，用通用名；格式归属在 `utils/subscription.py` 顶部 docstring 写清楚（"解析 Clash/Mihomo YAML 订阅与标准 URI 格式"）：

- `_parse_clash_yaml` → `parse_yaml`
- `_parse_clash_proxy` → `parse_proxy`
- 各 `_parse_clash_*` → 对应协议的通用名（`parse_ss` / `parse_vmess` / `parse_vless` …）

理由：格式向后兼容（Mihomo 沿用 Clash 的 YAML 结构，只增协议），名字无需绑定某个实现，docstring 统一说明即可。

### 跳过告警（可选）

放弃 ssr/anytls 后，`refresh_subscription` 可统计跳过的节点数并 `log('warn', ...)`，让用户知道「读了订阅、但这些协议不支持」，而非静默消失。放 service 层（低频，刷新时一次）。

---

## 实施顺序

| 步骤 | 动作 | 风险 |
|------|------|------|
| 1 | 协议精简（4 文件） | 低（删死分支 + 改 map） |
| 2 | URI 协议扩展（补 vless/trojan/hysteria2/tuic） | 中（新增 4 个 parser） |
| 3 | 解析下沉 utils（搬移 + 改名公开） | 中（纯搬移，需同步 import） |
| 4 | 通用命名 + 告警 | 低（命名 + 一行 log） |

每步独立 commit。

## 后续（不在本次范围）

- **`proxy-providers` 外部引用**：机场节点放在外部 YAML URL 的场景，需要时才做。

## 验证

```bash
python3 -m py_compile app/utils/subscription.py app/services/subscription_service.py
python3 -c "import app.routes"

# 逻辑验证（人工）：
# 1. 刷新一个含 ssr/anytls 节点的订阅 → 这些节点不出现（被跳过）
# 2. 刷新正常 vmess/vless/trojan/ss/hysteria2/tuic 订阅 → 节点正常入库
# 3. 刷新纯 URI 订阅（vless:// / trojan:// / hysteria2:// / tuic://）→ 节点正常入库
# 4. 手动创建 direct 节点（如支持）→ is_valid_protocol('direct') 仍 True
# 5. 启动一个 ss 节点服务 → 走 sslocal；hysteria2/tuic → 走 sing-box
```
