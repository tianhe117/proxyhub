# 端口分配统一

## 目标

两处端口分配逻辑统一为一个底层接口，用两个端口池隔离不同用途。

## 现状

| 位置 | 函数 | 用途 | 生命周期 |
|------|------|------|---------|
| `checker/checker.py` | `allocate_ports(n)` | URL 测试端口 | 短时，用完即释放 |
| `config_service.py` | `find_available_port()` | 服务 SOCKS5 端口 | 长期，进程存活期间占用 |
| `config_service.py` | `is_port_available()` | 入站端口检查 | — |

三处各自实现，逻辑重复。

## 设计

### 1. settings — 两个端口池（互不相交）

```python
# Service pool — 长期运行的 SOCKS5 端口
SOCKS_PORT_START = 50000
SOCKS_PORT_END   = 55000

# Test pool — 健康检查临时端口
TEST_PORT_START  = 55000
TEST_PORT_END    = 60000
```

### 2. app/port.py — 底层抽象（纯 stdlib）

```python
class PortPool:
    def __init__(self, start, end):
        self.start = start
        self.end   = end
        self.cursor = start

    def allocate(self, n=1) -> list[int]:
        """从游标开始顺序扫描可用端口，返回 n 个。"""
        # 游标推进，越界回绕到 start，避免重复用最近释放的端口

    def allocate_one(self) -> int:
        return self.allocate(1)[0]


def is_port_available(port, host='127.0.0.1') -> bool:
    """bind 探测端口是否可用。"""


# 单例池
service_pool = PortPool(SOCKS_PORT_START, SOCKS_PORT_END)
test_pool    = PortPool(TEST_PORT_START,  TEST_PORT_END)
```

### 3. 调用方适配

| 文件 | 改动 |
|------|------|
| `checker/checker.py` | 删 `allocate_ports`/`_try_port`/`_cursor`，改 `from app.port import test_pool`，`test_pool.allocate(n)` |
| `checker/__init__.py` | `from app.checker.checker import ... allocate_ports ...` 改为 `from app.port import test_pool` |
| `config_service.py` | 删 `find_available_port`/`is_port_available`/`random`，改 `service_pool.allocate_one()`；`check_inbound_port` 用 `is_port_available(port, '0.0.0.0')` |
| `service_manager.py` | import 从 `config_service.find_available_port` 改为 `app.port.service_pool.allocate_one()` |

## 验证

1. `python3 test/test_checker.py` — checker 批量测试用 test 池
2. 启动应用，创建服务 → 服务端口落在 50000-55000
3. 健康检查临时端口落在 55000-60000，两者不重叠
