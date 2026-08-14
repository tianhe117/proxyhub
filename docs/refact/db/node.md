# node.py 优化设计

## 现状

`app/db/node.py` 是标准的「一表一模块」函数式 CRUD，字段注释头已完整。8 个函数：

| 函数 | 作用 | 调用者 |
|------|------|--------|
| `list_all()` | 全量节点 | `api_nodes.py:56` |
| `list_by_sub(sub_id)` | 某订阅的节点 | `api_nodes.py:76`、`api_subscriptions.py:23` |
| `list_grouped()` | 按订阅分组 | `api_nodes.py:62` |
| `get_by_id(node_id)` | 单节点 | `api_nodes.py:123`、`node_service.py`、`outbound_service.py`、`config_service.py`、`service_manager.py` |
| `create(...)` | 插入 | `node_service.py:33` |
| `update(node_id, **fields)` | 白名单更新 | `node_service.py:49` |
| `delete(node_id)` | 删单节点 | `node_service.py:58` |
| `delete_all()` | 清空 | `node_service.py:64` → `api_nodes.py:109`（前端 clear 按钮） |

**结论：8 个接口全部有真实调用者，`delete_all` 需要保留**（`/api/nodes/clear` 前端「清空全部节点」用）。

## 发现的问题

### 1. `delete` 缺级联清理（真实隐患，建议修）

`db/node.py:delete` 只删 `nodes` 一行，未清理 `outbound_nodes` 池引用。对照 `db/subscription.py:delete_node` 已做级联：

```python
def delete_node(node_id):
    db.execute('DELETE FROM outbound_nodes WHERE node_id = ?', (node_id,))
    db.execute('DELETE FROM nodes WHERE id = ?', (node_id,))
```

后果：手动删节点后 `outbound_nodes` 留下孤儿行，`get_pool_nodes` 的 INNER JOIN 静默丢弃（界面不显示），但脏数据堆积。违反「引用完整性靠应用层维护」原则——此处漏了一处。

**方案**：`db/node.py:delete` 补 `DELETE FROM outbound_nodes WHERE node_id = ?`。

### 2. `delete` 的 single 引用校验（业务规则，建议在 service 层）

node 被 outbound 引用有两种，性质不同，**分层处理**：

| 引用类型 | 存储位置 | 处理层 | 动作 |
|---------|---------|--------|------|
| auto 池引用 | `outbound_nodes.node_id` | db 层 | 机械级联删除（问题 1） |
| single 引用 | `outbounds.config_json` 的 JSON `node_id` | service 层 | 校验后**拒绝删除** |

single 引用藏在 JSON 字符串里，检查需要 parse 所有 outbounds 比对 `node_id`，是业务决策，db 层不该管（只做 SQL）。

**方案（推荐 A：拒绝删除）**：`node_service.delete_node` 里先扫 outbounds，若某 `single` 出站的 `config_json.node_id == node_id`，返回 `{success: false, message: "该节点被出站 X 引用，请先修改/删除该出站"}`。

理由：静默悬空比显式报错难排查——现在悬空后，用户要到启动 service 时才看到莫名的 `"No node available for outbound"`，还不知道是哪个出站、为什么。其他两案（B 静默允许悬空=现状、C 级联清 JSON）都不推荐：B 排查体验差，C 会悄悄把出站变不可用，比拒绝更隐蔽。

需要的辅助查询放 `db/outbound.py`：`list_single_outbounds_by_node(node_id)` 或更通用的「返回所有 single 出站及其 node_id」。

### 3. `node_service.py` 有 3 个死 import（顺带修）

`node_service.py:6-7` import 了 `list_all as list_nodes`、`list_grouped`、`list_by_sub`，但三个都未使用（该文件只用到 `create/get_by_id/update/delete/delete_all`）。

**方案**：`node_service.py` 的 import 精简为只用到的 5 个。

### 4. `list_grouped` 空组不对称（低优先，倾向不动）

- `custom_nodes`（`sub_id=0`）有 `if custom_nodes:` 守卫，空则跳过。
- 订阅组 `for sub in list_all_subs()` 无守卫，空订阅也 `append({'nodes': [], 'count': 0})`。

影响极小，可能是刻意「订阅组要显示 0 节点」。**不改。**

### 5. `count` 冗余字段（不动）

`list_grouped` 的 `count` 恒等于 `len(nodes)`，但前端已依赖该 API 形状。**不改。**

## 改动清单

| 文件 | 改动 |
|------|------|
| `app/db/node.py` | `delete` 补 `DELETE FROM outbound_nodes WHERE node_id = ?` 级联 |
| `app/db/outbound.py` | 新增「查被某节点 single 引用的出站」辅助查询 |
| `app/services/node_service.py` | `delete_node` 加 single 引用校验（拒绝删除）；import 精简去掉 3 个死 import |

## 验证

```bash
# 编译 + import 冒烟
python3 -m py_compile app/db/node.py app/db/outbound.py app/services/node_service.py
python3 -c "import app.routes"

# 逻辑验证（依赖真实数据，人工核对）：
# 1. 建一个 auto 出站池引用某节点，删节点后 outbound_nodes 无孤儿
# 2. 建一个 single 出站指向某节点，删该节点应被拒绝并提示出站名
```
