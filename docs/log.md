# logger 设计（utils 叶子工具）

> 层级：工具层 / 日志。本文是 `app/utils/_logger.py` 的设计稿，承接[顶层设计](design.md)核心决策与 [`settings.md`](settings.md) 的路径布局。
> 状态：✅ 已编码。对外入口唯一：`from app.utils import log`。

## 1. 定位

`app/utils/_logger.py` 是日志叶子工具（**私有内部模块**，下划线前缀标识），只做一件事：把运行日志写到 `logs/` 目录下的本地文件。无引擎耦合、无第三方依赖（用 Python 标准库 `logging`）。

对外**只有一个接口 `log`，且只能通过 `app.utils` 调用**：调用方 `from app.utils import log` 之后，`log.info(msg)` / `log.error(msg)` 即可落盘，其余细节全部隐藏。`_logger.py` 不对外暴露，**禁止** `from app.utils.logger import log` 这类绕过方式。

## 2. 对外接口

```python
from app.utils import log

log.info('节点切换成功')     # 常规信息
log.error('订阅拉取失败')    # 错误
log.warning('...')          # 标准库自带，同理可用
log.debug('...')            # 默认级别 INFO，debug 不落盘
```

- **唯一入口**：`from app.utils import log`。`log` 由 `app/utils/__init__.py` 从私有模块 `_logger.py` 再导出（`__all__ = ['log']`）。
- `log` 是 `logging.Logger` 实例（标准库），`info` / `error` / `warning` / `debug` / `exception` 全部可用。
- 除 `log` 外**不对外暴露任何名字**（`_build_log` 等实现细节私有化，模块本身也私有化为 `_logger.py`）。

## 3. 日志格式

一行一条，字段依次为：**时间、level、接口名称、msg**。

```
[2026-08-18 12:34:56] [INFO] [switch_node] 节点切换成功
[2026-08-18 12:34:57] [ERROR] [pull_subscription] 订阅拉取失败
```

| 字段 | 取值 | 说明 |
|------|------|------|
| 时间 | `YYYY-MM-DD HH:MM:SS` | `datefmt='%Y-%m-%d %H:%M:%S'` |
| level | `INFO` / `ERROR` / `WARNING` / `DEBUG`（大写） | `%(levelname)s` |
| 接口名称 | 调用 `log` 的那个函数名 | `%(funcName)s`，见 §6 |
| msg | 调用方传入的原始字符串 | `%(message)s` |

- **接口名称 = 调用方函数名**：Flask 视图函数名即路由接口名，两者天然一致（如 `switch_node`、`api_get_nodes`）。由 `logging` 的 `%(funcName)s` 自动捕获，调用方无需传参。

## 4. 目录与文件名

- **目录**：`settings.get_logs_dir()`（即 `BASE_DIR/logs/`，可被 `PROXYHUB_HOME` 覆盖，Docker=volume）。不存在时 `os.makedirs(..., exist_ok=True)` 自动创建。
- **文件名**：**每次进程启动一个新文件**，按 `design.md` 约定 `YYYY-MM-DD_HHMMSS.log`（如 `2026-08-17_201500.log`）。时间戳取**模块导入那一刻**（= 应用启动时刻），一次进程只落一个文件。

## 5. 实现要点（代码草案）

```python
"""Internal file logger for ProxyHub (private — import via `app.utils` only).

Single public interface: `log` (a stdlib logging.Logger), re-exported from
app.utils:

    from app.utils import log
    log.info('node switched')
    log.error('pull failed')

This module is private (_logger.py); do not import it directly. Writes one
file per process start to settings.get_logs_dir(), named
YYYY-MM-DD_HHMMSS.log (per design.md). Each line records time, level,
caller function name (接口名称), and message.
"""

import logging
import os
from datetime import datetime

from app import settings


def _build_log():
    """Configure and return the process-wide logger (called once at import)."""
    os.makedirs(settings.get_logs_dir(), exist_ok=True)
    filename = datetime.now().strftime('%Y-%m-%d_%H%M%S') + '.log'
    path = os.path.join(settings.get_logs_dir(), filename)

    logger = logging.getLogger('proxyhub')
    if not logger.handlers:  # 防重：reload 时避免重复加 handler
        handler = logging.FileHandler(path, encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(funcName)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False  # 只落文件，不回传 root（避免 console/stderr 输出）
    return logger


log = _build_log()
```

## 6. 关键决策

| 决策 | 内容 | 理由 |
|------|------|------|
| 标准库 `logging` | 不引第三方依赖 | 叶子工具，够用且线程安全（Flask 多线程下无并发问题） |
| 只落文件 | `FileHandler` + `propagate=False` | 需求是「记录日志到本地」，不打印控制台 |
| 直接暴露 Logger | `log` 就是 Logger 实例，不包 helper 函数 | 若包一层函数，`%(funcName)s` 会捕获到 helper 名而非真实调用方 |
| 私有模块 + 单一出口 | `_logger.py` 私有化，`log` 只从 `app/utils/__init__.py` 导出 | 强制「只能通过 utils 调用」，杜绝 `from app.utils.logger import log` |
| 防重 | `if not logger.handlers` | `importlib.reload` 时不重复追加 handler / 不产生多余文件 |
| 级别默认 `INFO` | `logger.setLevel(logging.INFO)` | `debug` 默认不落盘；如需可后续加设置项，当前 YAGNI |
| 模块级导入即建文件 | `log = _build_log()` 在模块顶层执行 | 首次 import（= 启动）即确定本次文件名 |

## 7. 边界与后续

- **不落控制台**：开发期如需同时看 stdout，后续可加一个 `StreamHandler`，当前按需求只落盘。
- **无日志轮转**：一次进程一个文件，不做按大小/天数切分（单文件足够，避免引入 `RotatingFileHandler`）。
- **模块顶层调用**：在非函数上下文调用 `log.info(...)` 时 `%(funcName)s` 显示 `<module>`，属预期行为。
- 对应 [`refer.md` §9 复用清单](refer.md) 中的 `utils/logger.py`；v2 在此将其私有化为 `_logger.py`、对外收敛为 `app.utils` 的单一 `log`，并按启动时间命名文件。
