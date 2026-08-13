# services 层审查

## 现状

```
services/
├── auth_service.py        34行  认证 — 🟢 干净
├── config_service.py     166行  配置生成 — 🟡 有优化点
├── node_service.py        66行  节点业务 — 🟢 基本合格
├── outbound_service.py    87行  出站业务 — 🟢 基本合格
├── service_manager.py    722行  臃肿 ⚠️
├── subscription_service.py 588行 订阅解析（待审查）
└── upgrade_service.py    187行  升级 — 🟢 干净
```

## 小文件审查结论

### 🟢 无需改动

| 文件 | 说明 |
|------|------|
| `auth_service.py` | 认证逻辑简洁，无冗余 |
| `upgrade_service.py` | 下载/解压/插件处理完整，错误处理到位 |
| `node_service.py` | 验证 → CRUD → 统一 `{success, message}` 返回，结构清晰 |
| `outbound_service.py` | 同 node_service 模式，add_node_to_pool 有去重和存在性检查 |

### 🟡 小问题（不阻塞，可顺手改）

| 文件 | 问题 |
|------|------|
| `node_service.py` | `clear_all_nodes` 延迟导入 `delete_all`，顶部已有 `delete` 导入，风格不一致 |
| `outbound_service.py` | `reorder_pool`/`remove_node_from_pool` 无入参验证（空列表/不存在 id） |
| `config_service.py` | `is_port_available`/`find_available_port`（随机）与 `checker.allocate_ports`（顺序）是两套端口分配逻辑，**系统级重复** |

## 核心问题

1. **`service_manager.py` 职责过载（722 行）**——混了 4 类职责：
   - 服务启停：`start_service`/`stop_service`/`restart_service`/`_start_service_with_node`
   - failover 状态机：`_get_failover_state`/`_switch_to_node`/`_do_failover`
   - 两个 daemon：`start/stop/restart_health_check_daemon` + `start_auto_start_daemon`
   - 查询 API：`switch_node`/`get_current_node`

   建议拆分：
   ```
   services/
   ├── service_manager.py   # 服务启停 + 查询（~250行）
   ├── failover.py          # failover 状态机（~200行）
   └── health_daemon.py     # 两个 daemon（~200行，待重写）
   ```

2. **端口分配逻辑重复**——`config_service.find_available_port` vs `checker.allocate_ports`，两个独立实现，应统一。

## 建议顺序

| 步骤 | 动作 |
|------|------|
| 1 | 审查 `subscription_service.py`（588 行，独立性强） |
| 2 | 拆 `service_manager.py`（最后处理，daemon 待重写） |
| 3 | 统一端口分配逻辑 |
