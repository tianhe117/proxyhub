# Pool 首节点作为备选节点（Fallback）

## 背景

每个 auto 类型的出站有一个节点池（pool），按 priority 排序。当前 failover 逻辑：节点挂了之后，从 pool 中跳过当前节点、按序查找下一个可用节点。

问题：如果前几个节点都不稳定，failover 需要逐个探测，服务中断时间较长。

如果用户把稳定的备选节点 X 放到 pool[0]（最高优先级），那么故障时应该**无条件先切到 pool[0]**，保证可用性，再从 pool[1:] 慢慢找更好的节点。

## 设计

### 核心逻辑

```
当前节点挂了（达到 FAIL_THRESHOLD）
    │
    ├── 当前节点 ≠ pool[0]
    │     ├── 无条件切到 pool[0]（不检查健康，直接切）
    │     └── 从 pool[1:] 扫描更优节点
    │
    └── 当前节点 = pool[0]（已经在备选上）
          └── 从 pool[1:] 扫描其他可用节点
```

**不检查 pool[0] 的健康**：pool[0] 被定义为"稳定备选"，假定它基本不会不可用。如果 pool[0] 确实也挂了，切换到 pool[0] 后下一次健康检查会发现，再扫 pool[1:]。

### 改动范围

**仅 1 个文件 + 1 行前端，无数据库变更。**

### 1. `app/services/service_manager.py` — `_do_failover()` 改动

**现逻辑**（跳过 current_node_id，从 pool 头开始找第一个可用节点）：

```python
def _do_failover(outbound_id, pool, current_node_id):
    for entry in pool:
        nid = entry['node_id']
        if nid == current_node_id:
            continue
        # 逐个健康检查...
```

**新逻辑**：

```python
def _do_failover(outbound_id, pool, current_node_id):
    # pool[0] 为备选节点
    fallback_node_id = pool[0]['node_id']

    if current_node_id != fallback_node_id:
        # 不在备选上 → 无条件先切到 pool[0]
        _switch_to_node(outbound_id, fallback_node_id)
        # 然后从 pool[1:] 扫描更优节点
        for entry in pool[1:]:
            nid = entry['node_id']
            if nid == fallback_node_id:
                continue
            # 健康检查，找到可用 → 切过去 → return
    else:
        # 已在备选上 → 从 pool[1:] 扫描其他节点
        for entry in pool[1:]:
            # 健康检查，找到可用 → 切过去 → return

    # 全挂了 → 递增等待（原逻辑不变）
```

其中 `_switch_to_node` 是抽取的公共方法，把"重启该 outbound 下所有 running service 到指定节点"的逻辑独立出来。当前 `_do_failover` 和 `switch_node` 中已有重复代码。

### 2. 前端 pool 节点列表

pool 列表第一行（priority=1，最高优先级）旁增加 `备选` 标签（灰色小 tag），hover 提示：

> 备选节点：故障时优先回退到此节点。建议在此放置慢但稳定的节点。

### 3. 与现有优先节点恢复的配合

优先节点恢复逻辑不变（当前在 pool[0] 且正常时，`last_preferred_check` 清 0，因为 pool[0] 就是最高优先级，不存在"更优先"。已经在 pool[0] 上就不需要恢复了）。

## 不变的部分

- 数据库 schema 不变
- `FAIL_THRESHOLD`、`FAILOVER_CHECK_INTERVAL` 不变
- `all_dead_count` 递增等待逻辑不变
- `get_pool_nodes()` 不变
- API 接口不变
- 优先节点恢复逻辑不变
