# 健康检测重构 — 待完成优化项

**来源**: `d587097` + 未提交的 refactoring  
**文件**: `app/checker/__init__.py`, `app/services/service_manager.py`

---

## 已完成的改动（待 commit）

- `check_node_health(node, tag)` 提取为公共函数，`_run_checks` 和 failover daemon 共用
- `service_manager._check_node_health` 简化为 thin wrapper
- 清理 `service_manager.py` 无用 import（`os`, `DEFAULT_SETTINGS`, `generate_temp_config`, `find_temp_port`, `tcp_ping`, `url_test`）
- `check_node_health` 增加 `check_type` 参数支持（`'tcp'|'url'|'both'`）

---

## 待完成项

### 1. `_run_checks` 中 `check_type` 参数未穿透

**位置**: `checker/__init__.py:_run_checks`

`check_node_health` 已支持 `check_type`，但 `_run_checks` 接收到前端传来的 `check_type` 后硬编码调用 `check_node_health(node, tag)`，未传入 `check_type`。

**方案**: 改为 `check_node_health(node, tag, check_type)`

---

### 2. `checker/__init__.py` 未使用的 import 清理

当前 Pylance 告警：
- `json` — 未使用
- `get_bin_dir`、`get_config_dir` — 已从 `app.settings` 导入但未使用

---

### 3. Phase 1 和 Phase 3 共用同一个 `tag`

**位置**: `service_manager.py:584`

Phase 3（优先节点恢复扫描）复用 Phase 2 的 `tag` 变量。虽然当前串行执行没有问题，但隐式依赖同一 for 循环作用域。如果未来重构拆分阶段可能 NameError。

**方案**: Phase 3 独立生成自己的 tag。

---

## 与 todo/ 其他文档关系

- `todo/failover-phase3-optimization.md` — 更完整的 Phase 3 代码优化清单（8 项），本文档的 #3 与其 #8 重叠
- `todo/log-optimization.md` — 前端日志优化
