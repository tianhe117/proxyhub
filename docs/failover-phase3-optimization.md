# failover Phase 3 代码质量优化项

**来源**: `056d53d` 代码审查  
**文件**: `app/services/service_manager.py`  
**性质**: 全部为可维护性/效率优化，无功能性问题

---

## 优化项

### 1. 池扫描循环三处重复 — 提取公共函数

**位置**: `service_manager.py:207-226, 242-258, 623-637`

`_do_failover`（两处）和 Phase 3 实现了完全相同的模式：`get_node → _check_node_health → update_latency → break on healthy`。约 27 行重复代码。

**方案**: 提取 `_find_first_healthy(entries, tag)` → 返回 `(node_dict, health_dict)` 或 `(None, None)`。三处调用简化为一行。

---

### 2. enumerate + continue 改 slice

**位置**: `service_manager.py:623-627`

```python
# 当前
for i, entry in enumerate(pool):
    if i == 0: continue
    if current_idx > 0 and i >= current_idx: continue

# 改
end = current_idx if current_idx > 0 else len(pool)
for entry in pool[1:end]:
```

`current_idx == 0` 时的全扫描行为通过布尔短路隐含实现，改为 slice 使意图显式化。

---

### 3. 合并重复的 `if health['healthy']` 守卫

**位置**: `service_manager.py:594, 615`

Phase 2 的 `if health['healthy']:` (line 594) 和 Phase 3 的 `if health['healthy']:` (line 615) 重复。Phase 3 应合并回 Phase 2 的 healthy 分支内。

---

### 4. `.get()` 改直接访问

**位置**: `service_manager.py:620`

```python
# 当前
if now - state.get('last_preferred_check', 0) >= rec_int:

# 改
if now - state['last_preferred_check'] >= rec_int:
```

`last_preferred_check` 在 `_get_failover_state()` 中初始化为 0，永不删除。`.get()` 会在 key 意外缺失时静默掩盖 bug，与同文件其他 state 字段访问方式不一致。

---

### 5. Phase 3 优先 TCP 探测，跳过无效节点的 URL 测试

**位置**: `service_manager.py:631`

候选节点 TCP 不通时无需执行 URL 测试（fork 代理进程 + curl），直接跳过。当前对每个候选都执行完整的 `_check_node_health`。

**方案**: 在 `_check_node_health` 内部，TCP 不通时跳过 URL 测试（当前已如此）。此处扫描时可先做轻量 TCP ping，只有 TCP 通的才调用 `_check_node_health`。

---

### 6. `current_idx` 计算移入 interval 守卫内

**位置**: `service_manager.py:616-618`

```python
# 当前（每次 tick 都算）
current_idx = next(...)
if now - state['last_preferred_check'] >= rec_int:
    ...

# 改（仅 Phase 3 实际执行时算）
if now - state['last_preferred_check'] >= rec_int:
    current_idx = next(...)
    ...
```

Phase 3 每 180s 执行一次，但 `current_idx` 每 15s 都算一遍（12 次算 11 次白算）。

---

### 7. 减少候选节点的无效 DB 写入

**位置**: `service_manager.py:632-635`

不健康候选节点的延迟为 -1，此时 `update_latency()` 的 UPDATE+COMMIT 无意义。

**方案**: 仅在节点健康时写入延迟数据。

---

### 8. Phase 3 独立计算 tag

**位置**: `service_manager.py:584(定义), 631(使用)`

Phase 3 复用 Phase 2 的 `tag` 变量，隐式依赖同一 for 循环作用域。若未来重构拆分阶段可能 NameError。

**方案**: Phase 3 自行生成独立 tag。

---

## 优先级

| 优先级 | 编号 | 说明 |
|--------|------|------|
| P1 | 1, 2, 3 | 结构清晰度，直接改善代码可读性 |
| P2 | 4, 6, 8 | 小改动，消除隐患 |
| P3 | 5, 7 | 效率优化，pool 通常 2-3 个节点，实际影响小 |
