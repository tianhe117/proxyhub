# 代码评审

底层重构（db 外键化）完成后，对 `settings` / `utils` / `checker` / `db` 四个模块的完整评审。

按严重程度分级：**P1** 活跃 bug/隐患，**P2** 结构/一致性问题，**P3** 低优先/可接受。
每条末尾标注**处理决定**（含「已定待改」= 方向已确认，尚未动手；「接受不改」= 确认保持现状）。

---

## P1 — 活跃 bug / 隐患

### 1. `checker/checker.py:23` — `tcp_check` 连接失败时 socket 泄漏

```python
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(timeout)
sock.connect((address, int(port)))   # 这里抛异常 → sock 未 close
```

`connect()` 失败（超时/拒绝连接）时走 `except` 分支，但 `sock` 没有 `close()`。TCP 检查是**全节点并发、高频**执行，失败节点多时会累积泄漏的文件描述符。

> **处理：已定待改。** `tcp_check` 改 `try/finally` 确保 `sock.close()`。

### 2. `checker/service.py:56` — `check_node` 的 `timeout` 参数是死变量

```python
def check_node(nodes: list[dict], timeout=None) -> list[CheckResult]:
    tcp_to = int(get_setting('tcp_timeout') or DEFAULT_SETTINGS['tcp_timeout'])
    curl_to = int(get_setting('curl_timeout') or DEFAULT_SETTINGS['curl_timeout'])
    timeout = timeout or curl_to    # ← 赋值后从未使用
```

`timeout` 参数被 `checker/__init__.py` docstring 写成 `check_node(nodes, timeout=6)`，但传入值不影响任何逻辑。

> **处理：已定待改。** 删 `timeout` 参数 + `curl_to` + `timeout = timeout or curl_to` 三处（`curl_timeout` 已在 `_check_url_one` 内部读取，无需在 `check_node` 重复）。只保留 `tcp_to`。同步改 `checker/__init__.py` docstring。

---

## P2 — 职责重叠 / 一致性

### 3. `db/subscription.py` 混入节点 CRUD，与 `db/node.py` 重复

违反「一表一模块」约定，节点操作散在两个文件：

| subscription.py 里的函数 | node.py 的等价物 | 差异 |
|---|---|---|
| `get_nodes_by_sub(sub_id)` | `list_by_sub(sub_id)` | 完全重复 |
| `update_node(id, **fields)` | `update(id, **fields)` | 重复，且**缺 `config_json` dict→json 转换** |
| `delete_node(id)` | `delete(id)` | 重复，且**无 `commit()`** |

> **处理：已定待改。** 归并到 `node.py`：给 `node.update` / `node.delete` 加 `commit=True` 参数（默认落库，事务内传 `commit=False`）；`subscription.py` 删掉这三个函数，`sync_nodes` 改调 `node.list_by_sub` + `node.update/delete(commit=False)`。顺带修复 `config_json` 转换缺失。

### 4. `db/database.py:121` — `_seed_sentinels` docstring 已过时

```python
"""... They are read-only and filtered out of list_all()."""
```

上一轮已把 `list_all` 改成全量返回哨兵行，docstring 还写着 "filtered out"。

> **处理：已定待改。** 改为 "included in list_all(); delete() guards id=0"。

### 5. `db/outbound.py:104` — `add_pool_node` 的 `priority=0` 语义模糊

```python
def add_pool_node(outbound_id, node_id, priority=0):
    if priority == 0:   # 0 = 自动分配
        priority = max_p + 1
```

`priority=0` 被当成"未指定→自动分配"哨兵，导致无法显式指定 priority=0（最高优先级）。

> **处理：已定待改。** 改 `priority=None` 表示自动分配，`if priority is None:` 时才 `max_p + 1`。

---

## P3 — 低优先 / 可接受

### 6. `utils/latency.py` — 节点删除后 latency 不清理

`_latency` 只增不减，节点删除后残留其 `CheckResult`。

> **处理：接受不改。** 节点 <100 个，内存影响可忽略；且 `AUTOINCREMENT` 不复用 id，不会错读。

### 7. `utils/validators.py:6` — `is_valid_protocol` 不含 `direct`

`node.py` docstring 把 `direct` 列在协议里，但 `PROTOCOL_BIN_MAP` 没有 `'direct'`，`is_valid_protocol('direct')` 返回 `False`。

> **处理：已定待改（仅底层一行）。** `PROTOCOL_BIN_MAP['direct'] = 'xray'`（`engine/xray.py:_build_outbound` 已支持 direct→freedom）。**但「direct 成为一等节点协议 + 前后端统一处理」是上层重构**，需登记 upper-layer-todo：
> - `node_service.create_custom_node` 的 `if not address` 校验会拒绝 direct 节点（direct 无需 address/port）
> - 前端节点表单加 direct 选项
> - `config_service.get_outbound_node` 重写（现读旧 `outbound['type']`）
>
> 语义提醒：`service.outbound_id=0` 哨兵（"不走出站"）与 `protocol='direct'` 节点（"freedom 直连"）是**两个不同概念**，加这一行不会合并它们；是否统一是上层建模决策。

### 8. `db/subscription.py:125` — `sync_nodes` 用 `name` 作 key，同名节点覆盖

`old_map = {n['name']: dict(n) ...}`，同名节点 dict 丢一个。

> **处理：已定待改（归并 + 明确语义，不换算法）。** `name` 匹配**保留**——它的核心价值是保住 node id 稳定，从而保住 `outbound_nodes`/`outbound_fallback` 的引用不被 CASCADE 清掉；若改全删重建则引用全失效。真正要改的是：
> - 配合第 3 条归并，`sync_nodes` 改用 `node.update/delete(commit=False)`，消除 commit 分散
> - 明确 `new_map` 同名取后者（dict 后覆盖前）
> - `_parse_content` 解析层加 name 去重保护（供应商数据异常的边界，不该靠 sync 层换 key）

### 9. `settings.py` — 值统一字符串，数字需调用方 `int()`

`set_setting` 强制 `str(value)`，数字配置散落 `int(get_setting(...))`。

> **处理：已定待改。** 纯数字统一成 int，由 DEFAULT 值类型驱动 coerce：
> - `DEFAULT_SETTINGS` 数字字段改成 int（`check_interval_normal: 240` 等）
> - 新增 `_coerce(key, value)`：默认值是 int 就 `int(value)`，否则 `str(value)`
> - `set_setting` / `update_settings` / `_load_from_disk` 三处统一走 `_coerce`（`_load_from_disk` 必须也 coerce，否则旧 setting.json 的字符串不生效）
> - 向后兼容：现有 `int(get_setting(...))` 包一层无害，可后续清理

### 10. `utils/port.py:25` — `_available` 是 TOCTOU 竞态

bind 检查后立刻 close，检查到分配之间端口可能被抢。

> **处理：接受不改。** `allocate_ports` 的 cursor 递增保证本进程内不重复；外部抢端口在单用户 + 大端口范围（50000-55000）下概率可忽略。

---

## 处理汇总

| # | 决定 |
|---|---|
| 1 | 改：socket try/finally |
| 2 | 改：删 timeout 参数 + curl_to + 死赋值 |
| 3 | 改：节点 CRUD 归并到 node.py（commit 参数） |
| 4 | 改：_seed_sentinels docstring |
| 5 | 改：priority=None 表示自动 |
| 6 | 不改：接受 |
| 7 | 改（底层一行 direct）+ 上层登记 upper-layer-todo |
| 8 | 改：归并 + 明确同名语义（name 匹配保留） |
| 9 | 改：数字字段 int 化（DEFAULT 类型驱动 coerce） |
| 10 | 不改：接受 |
