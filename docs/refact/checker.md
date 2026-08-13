# checker 最终架构

## 目标

薄 `__init__.py` 聚合导出，内部按职责拆 3 个模块。对外接口稳定，内部实现自由重组。

```
app/checker/
├── __init__.py     # 聚合导出（纯接口表，无业务逻辑）
├── model.py        # CheckResult — 数据类型
├── service.py      # check_node + _check_url_one — 业务编排
└── checker.py      # tcp_check / url_check — 底层原语
```

## 依赖分层

```
checker.py   ← stdlib only (socket, subprocess, json, time) — 零项目依赖
model.py     ← dataclasses — 零项目依赖
service.py   ← checker.py + model.py + engine + settings — 业务编排
__init__.py  ← service.py + model.py — 聚合导出
```

依赖方向单向：`__init__` → `service` → `checker`。无环。

## 各模块内容

### model.py — CheckResult

```python
@dataclass
class CheckResult:
    success: bool
    tcp_latency_ms: int
    url_latency_ms: int
    http_code: str
    error: str
```

### checker.py — 底层原语（纯 stdlib）

```python
tcp_check(address, port, timeout=3)         → CheckResult
url_check(config, type, bin, port, url, timeout, tag) → CheckResult
```

- `tcp_check`：纯 Python socket connect，零 subprocess
- `url_check`：入参与 `proxy_url_check.sh` 的 7 个参数一一对应，只做 subprocess 调用 + JSON 解析

### service.py — 业务编排

```python
def check_node(nodes: list[dict], timeout=None) -> list[CheckResult]:
    """批量 TCP→URL 两阶段并发。

    - 内部从 settings 读 tcp_timeout / curl_timeout / test_url
    - phase 1: TCP 全部并发
    - phase 2: URL 并发（跳过 TCP 失败的），端口 test_pool 一次性分配
    """

def _check_url_one(node: dict, port: int) -> CheckResult:
    """config 生成 → url_check → 清理。"""
```

### __init__.py — 聚合导出

```python
from .checker import tcp_check, url_check
from .model import CheckResult
from .service import check_node

__all__ = ['check_node', 'CheckResult']
```

## 对外契约

外部调用不变：

```python
from app.checker import check_node, CheckResult
```

`__init__.py` 只导出公共接口（`check_node` + `CheckResult`），内部实现（`tcp_check`/`url_check`/`_check_url_one`）不对外承诺，可随时重组。

## 文件变更

| 操作 | 文件 | 内容 |
|------|------|------|
| 新增 | `app/checker/model.py` | CheckResult（从 checker.py 拆出） |
| 新增 | `app/checker/service.py` | check_node + _check_url_one（从 __init__.py 移入） |
| 精简 | `app/checker/__init__.py` | 变为纯聚合导出 |
| 精简 | `app/checker/checker.py` | 去掉 CheckResult，保留 tcp_check / url_check |

## 验证

```bash
python3 test/test_checker.py   # 全链路测试
python3 -c "from app.checker import check_node, CheckResult"  # 对外契约不变
```
