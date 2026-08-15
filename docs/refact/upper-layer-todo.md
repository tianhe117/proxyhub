# 底层重构 → 上层待适配清单

底层（db 层 schema + 迁移）已完成几处结构变更，上层（service / routes / 前端）仍引用旧字段，**运行时才崩，import 不崩**。按约定「db 上层只要语法没问题即可，后面整层重写」，本清单逐项追踪，待上层重写时一并处理。

## 1. outbound 建模：删 `type` / `config_json`

**底层已完成**：`outbounds` 表只剩 `id + name`；节点关系全在 `outbound_nodes` 表；direct 改 `service.outbound_id = 0`。

**待适配**：

| 文件 | 待改 |
|------|------|
| `services/config_service.py` | `get_outbound_node` 仍读 `outbound['type']`/`outbound['config_json']`（L38/42/48）。改为：`outbound_id==0` → 合成 direct 节点；否则按 `outbound_nodes` 关联数（1→single，≥2→auto pool[0] 或 failover 覆盖） |
| `services/service_manager.py` | `outbound['type'] == 'auto'/'direct'/'single'`（L319/485/646/681/684）。auto 判断改「关联节点数 ≥2」，direct 判断改 `outbound_id==0` |
| `services/outbound_service.py` | `create_outbound(name, out_type, config_json)` 签名 + `out_type` 三值校验 + config_json 解析（L13/17/20-28）。改 `create_outbound(name)`，删类型校验 |
| `routes/api_outbounds.py` | `TYPE_ORDER` 排序（L18/38）、`data.get('config_json')`（L48）。改按 id/name 排序，create/update 去 config_json |
| 前端 `templates/outbounds.html` | type 下拉、`o.type` 判断、`config_json` 读写（L23/144-154/195-285）。改：outbound 只管理名称+节点池；direct 移到 service 下拉 |
| 前端 `templates/dashboard.html` | `ob.type` 显示（L119/169）。service 的 Outbound 下拉加 `<option value="0">Direct</option>` |

## 2. latency 移内存：`update_latency` 死代码

**底层已完成**：`db/node.py` 删 `update_latency`，改 `utils/latency.py` 内存接口（`get_latency`/`update_latency`，入参 `CheckResult`）。

**待适配**：

| 文件 | 待改 |
|------|------|
| `services/service_manager.py` | L176/209/540/584 四处 `update_latency(...)` 调用引用未定义名（`NameError`）。均在不启动的 health-daemon / failover 路径，属死代码，待整文件重写时删除或改内存接口 |

## 3. services.status 移出 DB ✅ 已适配

`services` 表删 `status` 列，改实时查进程（`process.manager.is_service_running`）。`service_manager.py` 已改完，无需再动。

## 4. 池排序：删 reorder，统一走 sync

**后端已完成**：`reorder_pool_nodes`（db）、`reorder_pool`（service）、`/nodes/reorder`（routes）已删除。排序统一用 `sync_pool_nodes(outbound_id, node_ids)`（入参为 node_id 列表，全量替换）。

**待适配（影响前端排序）**：

| 文件 | 待改 |
|------|------|
| 前端 `templates/outbounds.html` | `_savePoolOrder()`（L304-310）仍调已删除的 `/nodes/reorder`，`movePoolToIndex()`（L312+）基于 `pool_id` 拖动排序。改为：拖拽后算出完整 `node_id` 列表，POST `/nodes/sync` |

> 排序语义不变（都是改 `priority` 影响 failover 顺序），只是从「增量 UPDATE pool_id」改为「全量 sync node_id」。

## 5. fallback 独立表：快速切换节点

**底层待实现**：新增 `outbound_fallback` 表（`outbound_id` 主键 + `node_id`），fallback 节点独立于 `outbound_nodes` 候选池。db 层需新增 `get_fallback_node(outbound_id)` / `set_fallback_node(outbound_id, node_id)` 接口。

**待适配（上层重写时）**：

| 文件 | 待改 |
|------|------|
| `services/service_manager.py` | failover 从「`pool[0]`=fallback、`pool[1:]`=候选」隐式切片，改为显式 `get_fallback_node()` + `get_pool_nodes()` 两个变量 |
| `routes/api_outbounds.py` | 新增 set/get fallback 路由 |
| 前端 `outbounds.html` | 新增 fallback 选择器（候选池与切换节点分开选择） |

> 语义：fallback 是独立的快速切换节点，不在候选池里；A 挂了先切到 fallback，再扫候选池找可用节点。

## 6. 引用完整性外键化：删除策略待定

**底层待实现**：所有引用关系声明外键（`nodes.sub_id`、`outbound_nodes`、`outbound_fallback`、`services.inbound_id/outbound_id`），删除时由 DB 自动级联或拦删；`direct`/`custom` 升级为 `id=0` 哨兵行。见 `docs/refact/db/referential-integrity.md`。

**待适配（上层重写时）**：

| 文件 | 待改 |
|------|------|
| `services/node_service.py` | `delete_node` 现有「检查引用并拒绝」逻辑（`list_outbounds_by_node`）与外键 CASCADE 语义冲突。定：删除节点是否静默级联（删池/fallback 引用，不拦），或降级为前端删除前确认弹窗 |
| `db/outbound.py` | `list_outbounds_by_node` 去留：若不再做后端拒绝，则删；若保留「误删提示」，改前端确认用（列出引用该节点的出站名） |
| `services/outbound_service.py` | `delete_outbound` 是否加「被 service 引用则拦」（外键 RESTRICT 会在 DB 层抛 IntegrityError，需在 service 层捕获转友好提示） |

> 外键只保证「不留孤儿 / 不静默破坏引用」，**不决定**「用户删时要不要先拦一下提示」。后者是应用层策略，此处登记，待上层重写时定。

---

## 约定

- 底层改动只保证 `import app.routes` 不崩 + `py_compile` 通过；上层旧字段引用允许存在，直到整层重写。
- 每完成一处底层结构变更，同步在本清单登记「待适配」项，避免遗漏。
