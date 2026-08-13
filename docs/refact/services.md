# services 层重构方案

## 现状

```
services/
├── auth_service.py        34行  认证
├── config_service.py     166行  配置生成（调 engine）
├── node_service.py        66行  节点业务（薄 CRUD）
├── outbound_service.py    87行  出站业务（薄 CRUD）
├── service_manager.py    722行  ⚠️ 启停+failover+2daemon+查询
├── subscription_service.py 588行 订阅解析
└── upgrade_service.py    187行  升级
```

## 核心问题：三层职责混在一起

| 类别 | 文件 | 特征 |
|------|------|------|
| 业务验证层 | node_service / outbound_service / auth_service | 薄，验证 + CRUD 透传，返回 `{success, message}` |
| 编排层 | service_manager | 厚，协调 db/engine/process/checker |
| 解析/工具层 | subscription_service / upgrade_service | 独立，协议解析 / 下载解压 |

## 目标结构

```
services/
├── resource_service.py       # 薄 CRUD 层合并（node + outbound + auth）
├── config_service.py         # 配置生成（不动）
├── service_manager.py        # 服务启停 + 查询（拆后 ~250行）
├── failover.py               # failover 状态机（从 service_manager 拆出）
├── health_daemon.py          # 两个 daemon（从 service_manager 拆出，待重写）
├── subscription/
│   ├── __init__.py
│   ├── parser.py             # 订阅解析主入口
│   └── parsers.py            # 各协议解析函数（clash/standard/vmess/ss...）
└── upgrade_service.py        # 升级（不动）
```

## 各步骤

### 1. 合并薄 CRUD 层 → `resource_service.py`

`node_service.py`（66）+ `outbound_service.py`（87）+ `auth_service.py`（34）合并为一个文件。

理由：三者都是"验证 → CRUD → 返回 `{success, message}`"的薄封装，模式完全一致，合并后约 180 行，一眼可见模式。

```python
# resource_service.py
# 认证
def is_authenticated(): ...
def login(username, password): ...
def logout(): ...

# 节点
def create_node(...): ...
def update_node(...): ...
def delete_node(...): ...
def clear_all_nodes(): ...

# 出站
def create_outbound(...): ...
def update_outbound(...): ...
def delete_outbound(...): ...
def add_node_to_pool(...): ...
...
```

调用方适配：`from app.services.node_service import ...` / `from app.services.outbound_service import ...` / `from app.services.auth_service import ...` → 统一 `from app.services.resource_service import ...`。

### 2. 拆 `service_manager.py` → 3 文件

```
service_manager.py   # 服务启停 + 查询（start/stop/restart/_start_service_with_node/switch_node/get_current_node）
failover.py          # failover 状态机（_get_failover_state/_switch_to_node/_do_failover + 常量）
health_daemon.py     # 两个 daemon（start/stop/restart_health_check_daemon + start_auto_start_daemon）
```

依赖：`service_manager` ← `failover`（启停时切换节点用到）；`health_daemon` ← `service_manager` + `failover`（循环监控）。

daemon 反正要重写，拆的时候先纯搬移，行为不变。

### 3. 拆 `subscription_service.py` → `subscription/` 子包

588 行主要是各协议解析（20 个 `_parse_clash_*` 函数）。拆成：

```
subscription/
├── __init__.py    # refresh_subscription 主入口
├── parser.py      # 解析分派（standard/vmess/ss/clash）
└── parsers.py     # 各协议具体解析函数
```

独立性强，风险低。

## 实施顺序

| 步骤 | 动作 | 风险 |
|------|------|------|
| 1 | 合并薄 CRUD 层 → `resource_service.py` | 低（纯搬移） |
| 2 | 拆 `subscription_service.py` | 低（独立性强） |
| 3 | 拆 `service_manager.py` → 3 文件 | 中（daemon 待重写，纯搬移先行） |

## 验证

1. 启动应用，节点/出站/服务/订阅 CRUD 正常
2. 服务启停正常（拆 service_manager 后）
3. 订阅刷新正常（拆 subscription 后）
