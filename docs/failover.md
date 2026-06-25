# 出站节点自动故障切换 v6

## 核心设计

**单线程轮询**。复用现有健康检查线程，每 15s 触发一次，先检查进程存活，再检查节点健康。

没有锁，没有并发，所有操作串行执行。

## 主循环

```
health_check_loop (每 15s)
  │
  ├─ 第一阶段：进程存活检查（所有服务）
  │    └─ 进程异常 → kill 残留 → 重启
  │
  ├─ 第二阶段：节点健康检查（仅 auto 类型 + 进程正常的服务）
  │    │
  │    ├─ 当前服务上次检查距今 < interval → 跳过，看下一个
  │    │
  │    └─ 到了检查时间 → 执行检查
  │         │
  │         ├─ 验证 current_node_id 还在 pool 中
  │         │   └─ 不在 → 重置 current_node_id = pool[0], fail_count = 0
  │         │
  │         ├─ current_node_id == 0 → 用 pool[0] 初始化
  │         │
  │         ├─ 测当前节点（TCP + curl）
  │         │   ├─ 正常 → fail_count = 0, interval = 240s
  │         │   └─ 失败 → fail_count += 1
  │         │       ├─ < 3 次 → interval = 30s
  │         │       └─ ≥ 3 次 → 触发切换
  │         │
  │         └─ 切换
  │              ├─ 扫描 pool 所有节点（TCP + curl）
  │              ├─ 找第一个健康的（跳过 current_node_id）
  │              │   ├─ 找到了 → 更新 current_node_id → stop → start
  │              │   └─ 全挂了 → 递增等待 5min → 10min → 15min → 30min
  │              └─ 继续检查下一个服务
  │
  └─ 本轮结束，等 15s
```

## 关键机制

### 跳过未到时间的服务

每个服务记录 `last_check` 时间戳。15s 触发一次，但只在 `now - last_check >= interval` 时才真正检查。

```
服务 A: last_check=60s前, interval=240s → 跳过
服务 B: last_check=35s前, interval=30s  → 到了，检查
服务 C: last_check=250s前, interval=240s → 到了，检查
```

这样 15s 的触发频率保证了响应速度，但不会对同一个服务重复检查。

### 单线程串行

所有操作都在同一个线程里：
- 测节点是串行的（一个测完再测下一个）
- 切换是串行的（stop → start 完成后再检查下一个服务）
- 不需要锁，不会有竞态

## 内存状态

```python
_failover_state = {}  # {service_id: {...}}

# 每个 service_id:
{
    'fail_count': 0,          # 连续失败次数 0~3
    'current_node_id': 0,     # 当前节点，上电=0，首次检查取 pool[0]
    'last_check': 0,          # 上次检查时间戳
    'interval': 30,           # 当前间隔，上电初始化 30s（快速）
    'all_dead_count': 0,      # 全挂了连续次数
}
```

## 判断标准

切换时对 pool 中每个节点执行 TCP + URL 两项检测：

- **TCP ping**：直接 socket connect，验证网络可达
- **URL test**：通过临时代理 curl 测试 URL，验证代理链路可用

TCP 通不代表代理可用，必须两项都通过才算健康。

从 nodes 表读 `tcp_latency` 和 `curl_latency`：

| 值 | 含义 |
|------|------|
| `NULL` | 从未检测过，**视为可用** |
| `> 0 且 ≤ timeout` | 正常 |
| `== -1` 或 `> timeout` | 不通 |

阈值：`tcp_timeout = 3s`, `curl_timeout = 5s`。两个都正常才算可用。

## 三次确认

```
正常周期 = 240s
         ↓ 第 1 次失败
快速周期 = 30s
         ↓ 第 2 次失败
快速周期 = 30s
         ↓ 第 3 次还失败 → 确认不可用 → 切换

中间任意一次恢复 → fail_count = 0，回正常周期
```

## 全挂了递增等待

```python
ALL_DEAD_INTERVALS = [5*60, 10*60, 15*60, 30*60]  # 5min, 10min, 15min, 30min
```

```
第 1 次全挂 → interval = 5min
第 2 次全挂 → interval = 10min
第 3 次全挂 → interval = 15min
第 4 次及以后 → interval = 30min（封顶）

有节点恢复 → all_dead_count = 0, interval 切回正常
```

## 切换动作

```python
# 1. 扫描 pool 所有节点（TCP + URL test）
for entry in pool:
    if entry['node_id'] == current_node_id:
        continue
    # TCP ping
    tcp = tcp_ping(entry['address'], entry['port'], tcp_timeout, tag)
    # URL test（需要临时配置文件 + 临时端口 + 二进制路径）
    if tcp['success']:
        node = get_by_id(entry['node_id'])
        config, filename = build_outbound_config(node, temp_port)
        config_path = save_temp_config(config)
        url = url_test(config_path, node['bin_type'], bin_path, temp_port, test_url, curl_timeout, tag)
    # 写入 nodes 表
    update_latency(entry['node_id'], tcp['latency_ms'], url['latency_ms'], now)

# 2. 找第一个 TCP + curl 都健康的
new_node_id = find_first_healthy(pool, skip=current_node_id)

# 3. 更新 current_node_id
_failsafe_state[service_id]['current_node_id'] = new_node_id

# 4. stop → start
stop_service_processes(service_name)
node = get_by_id(current_node_id)
start_service(service_id)  # 内部用 get_outbound_node(outbound, node_id=current_node_id)

# 5. 重置
fail_count = 0, all_dead_count = 0, interval = 240s
```

### URL test 基础设施

切换时需要为每个节点生成临时配置并启动临时代理。复用 checker 的私有函数：
- `checker/__init__.py` 的 `_generate_temp_config()` 和 `_find_temp_port()`
- 改为公共函数，或在 service_manager 中复制逻辑

## 日志规范

Web 日志页面可直接查看：

```
[warn] failover: socks: node 日本01 连续3次不可用 (tcp=3001ms, curl=-1ms)，扫描 pool 中 5 个节点...
[info] failover: socks: 选定节点 日本03 (tcp=120ms, curl=230ms)
[ok]   failover: socks: 已切换到 日本03

全挂了：
[warn] failover: socks: 所有节点不可用，5 分钟后重试

当前节点被用户删除：
[info] failover: socks: current_node_id 不在 pool 中，重置为 pool[0]
```

## 需要改的文件

| 文件 | 改动 |
|------|------|
| `services/service_manager.py` | 现有健康检查线程扩展：先检查进程存活，再检查节点健康 + `_failover_state` + 切换逻辑 |
| `services/config_service.py` | `get_outbound_node()` 加 `node_id` 参数 |
| `checker/__init__.py` | `_generate_temp_config()` 和 `_find_temp_port()` 改为公共函数 |
| `routes/api_services.py` | 新增 `GET /api/services/<id>/current-node` 返回当前节点 |
| 前端（节点列表） | 从 API 获取当前节点标绿 |

## 不需要改的

| 项 | 原因 |
|------|------|
| `database.py` | 不落库 |
| `models/service.py` | 无新字段 |
| 状态码 | `running` 不变 |
| 锁/线程安全 | 单线程串行，不需要 |
| 新增线程 | 复用现有健康检查线程 |
