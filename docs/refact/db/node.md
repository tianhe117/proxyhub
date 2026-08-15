# node.py 接口盘点

## 现状

`app/db/node.py` 是标准的「一表一模块」函数式 CRUD，字段注释头已完整。8 个函数：

| 函数 | 作用 | 调用者 |
|------|------|--------|
| `list_all()` | 全量节点 | `api_nodes.py:56,124` |
| `list_by_sub(sub_id)` | 某订阅的节点 | `api_nodes.py:75`、`api_subscriptions.py:23`、`node.py:47,53`（`list_grouped` 内部） |
| `list_grouped()` | 按订阅分组 | `api_nodes.py:62` |
| `get_by_id(node_id)` | 单节点 | `api_nodes.py:122`、`node_service.py:38,53`、`outbound_service.py`、`config_service.py`、`service_manager.py` |
| `create(...)` | 插入 | `node_service.py:33` |
| `update(node_id, **fields)` | 白名单更新 | `node_service.py:49` |
| `delete(node_id)` | 删单节点 | `node_service.py:63` |
| `delete_all()` | 清空 | `node_service.py:69` → `api_nodes.py:108`（前端 clear 按钮） |

**结论：8 个接口全部有真实调用者，`delete_all` 需要保留**（`/api/nodes/clear` 前端「清空全部节点」用）。

## 引用完整性（已由外键接管）

删除节点的级联清理**不再由 `node.py` 手写**——外键 `ON DELETE CASCADE` 已在 `database.py` 声明，`DELETE FROM nodes` 时 DB 自动清 `outbound_nodes` / `outbound_fallback`。设计见 [`referential-integrity.md`](referential-integrity.md)。

因此 `node.py:delete` / `delete_all` 只需删 `nodes` 本身，无需手写 `DELETE FROM outbound_nodes` / `outbound_fallback`；`subscription.py` 的删除路径同理，交由外键级联。

## 删除策略（应用层，待定）

`node_service.delete_node` 是否在删除前「检查引用并拒绝」、`db/outbound.py:list_outbounds_by_node` 的去留，属**应用层策略**（外键 CASCADE 只保证不留孤儿，不决定是否拦删）。已登记到 [`upper-layer-todo.md`](../upper-layer-todo.md)，待上层重写时定。

## 历史问题状态

| 历史问题 | 状态 |
|---|---|
| `delete` 缺级联清理 | ✅ 已由外键 `ON DELETE CASCADE` 解决 |
| `single` 引用校验（拒绝删除） | ✅ 已过时（outbound 建模重构后 single 消失，改纯关系） |
| `node_service.py` 3 个死 import | ✅ 已修（现只 import 用到的 5 个 + `list_outbounds_by_node`） |
| `list_grouped` 空组不对称 | ✅ 已修（custom 组与订阅组均加 `if nodes` 守卫） |
| `count` 冗余字段 | ✅ 已删（`list_grouped` 不再返回 `count`） |
