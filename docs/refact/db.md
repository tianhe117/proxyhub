# db 层优化方案

## 结论

**db 层保持函数式接口，不做 Repository 类封装。**

`app/db/node.py` 等模块本质上已是「一表一模块」的 Repository —— `list_all` / `get_by_id` / `create` / `update` / `delete` 五个动词 + 各表特殊方法。类封装（`node_repo.get()` 替代 `from app.db.node import get_by_id`）只是把 `import` 换成「类→单例→方法」的间接，零新能力，却要改 20+ 文件、引入一套新约定。

Repository 模式的三个价值点本项目都不沾：

- 多数据源可替换（SQL → PG）：SQLite 唯一，不会换
- 依赖注入 + mock 测试：测试是 checker 跑真实二进制，不 mock db
- 团队统一约定 + IDE 补全：单人 + Claude，模块前缀已消除歧义

## 保留：延迟字段移内存（延后）

真正有价值的重构是「延迟字段不落库、改存内存」，但它与健康检查流程强耦合，**延后到 health-daemon 重写时一起做**：

- `nodes` 表删除 `tcp_latency` / `curl_latency` / `last_check_at` 列（schema v2）
- `NodeRepo`（现 `db/node.py` 的 `update_latency`）删除
- 延迟改存内存 state，随 health-daemon 重写一并落地

延后理由：latency 的读写（`api_nodes` 展示、`get_pool_nodes` 的 JOIN、failover 的 `update_latency`）全在健康检查流程里，当前 health-daemon 已禁用，底层未稳定就动 schema 会两头改。
