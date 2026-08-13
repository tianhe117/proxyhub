# utils 层重构方案

## 目标

`app/utils/` 承载所有"无业务依赖的底层工具"。按功能拆文件，`__init__.py` 聚合对外接口。

## 目录结构

```
app/utils/
├── __init__.py     # 对外唯一入口，聚合导出
├── textkit.py      # split_keywords — 文本处理
├── format.py       # format_size — 格式化
├── validators.py   # 校验：协议/端口/bin_type
├── port.py         # PortPool + is_port_available
└── logger.py       # 日志（从 app/logger.py 迁入）
```

## __init__.py 聚合

```python
from .textkit import split_keywords
from .format import format_size
from .validators import (
    is_valid_protocol, is_valid_inbound_protocol,
    is_valid_port, is_valid_bin_type,
)
from .port import PortPool, is_port_available, service_pool, test_pool
from .logger import log, web_logger

__all__ = [...]
```

调用方统一 `from app.utils import ...`，内部拆分不影响外部。

## 模块职责与依赖

| 模块 | 内容 | 依赖 |
|------|------|------|
| `textkit.py` | `split_keywords(text)` | 无 |
| `format.py` | `format_size(num_bytes)` | 无 |
| `validators.py` | 5 个校验函数 | settings（协议常量） |
| `port.py` | `PortPool` 类 + `is_port_available` + 两个池单例 | settings（端口区间） |
| `logger.py` | `log()`/`web_logger` | settings（日志目录） |

依赖方向**单向**：utils → settings。无环。

## 原 helpers.py 拆分

`helpers.py` 两个函数职责不同，拆成 `textkit.py` + `format.py`：

- `format_size` → `format.py`
- `split_keywords` → `textkit.py`

## logger 迁入

`git mv app/logger.py app/utils/logger.py`，全局替换 import：

```
from app.logger import ...  →  from app.utils import ...
```

影响 9 个文件：`process/manager.py`、`routes/__init__.py`、`routes/api_logs.py`、`routes/api_system.py`、`services/config_service.py`、`services/node_service.py`、`services/service_manager.py`、`services/subscription_service.py`、`services/upgrade_service.py`。

## port.py — 端口池（配合 port-pool 方案）

```python
class PortPool:
    def __init__(self, start, end):
        self.start = start
        self.end   = end
        self.cursor = start

    def allocate(self, n=1) -> list[int]:
        """顺序扫描可用端口，游标推进，越界回绕。"""

    def allocate_one(self) -> int:
        return self.allocate(1)[0]


def is_port_available(port, host='127.0.0.1') -> bool:
    """bind 探测端口是否可用。"""


service_pool = PortPool(SOCKS_PORT_START, SOCKS_PORT_END)
test_pool    = PortPool(TEST_PORT_START,  TEST_PORT_END)
```

调用方切换：

| 文件 | 旧 | 新 |
|------|----|----|
| `checker/checker.py` | `allocate_ports`/`_try_port`/`_cursor` | `test_pool.allocate(n)` |
| `config_service.py` | `find_available_port`/`is_port_available` | `service_pool.allocate_one()`/`is_port_available` |
| `service_manager.py` | `find_available_port` | `service_pool.allocate_one()` |

## settings 不动

`app/settings.py` 保持顶层。它是基础设施不是工具，utils 各模块依赖它。

## 实施顺序

1. `git mv app/logger.py app/utils/logger.py` + 全局替换 import
2. 原 `helpers.py` 拆成 `textkit.py` + `format.py` + 更新 import
3. 新建 `app/utils/port.py`
4. `checker.py` / `config_service.py` / `service_manager.py` 切换端口池
5. `__init__.py` 聚合导出，替换各文件 import

## 验证

1. `python3 test/test_checker.py` — checker 用 test_pool
2. 启动应用 — 服务端口落 50000-55000，测试端口落 55000-60000
3. 日志正常输出（logger 迁移后）
