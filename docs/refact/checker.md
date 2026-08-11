# checker 最终架构

## 目标

```
app/checker/
├── __init__.py   # check_node + _check_url_one，有 DB/settings/engine 依赖
└── checker.py    # 纯 stdlib 底层函数，零外部依赖
```

## checker.py — 纯 stdlib

只依赖 Python 标准库（`socket`、`subprocess`、`json`、`time` 等）。可以脱离整个项目直接 import 和测试。

```python
CheckResult              # dataclass
allocate_ports(n)        # 端口分配 (socket bind)
tcp_check(addr, port, to) # 纯 Python socket connect
url_check(config, type, bin, port, url, timeout, tag)  # subprocess 调 proxy_url_check.sh
```

**url_check**：入参与 `proxy_url_check.sh` 的 7 个参数一一对应，只做 subprocess 调用 + JSON 解析，不碰 config 生成。

## __init__.py — 业务入口

有 DB、settings、engine 依赖。两个函数：

```python
def check_node(nodes: list[dict], timeout=None) -> list[CheckResult]:
    """批量 TCP→URL 两阶段并发。

    - 内部从 settings 读 tcp_timeout / curl_timeout / test_url
    - phase 1: TCP 全部并发
    - phase 2: URL 并发（跳过 TCP 失败的），端口一次性分配
    """
```

```python
def _check_url_one(node: dict, port: int) -> CheckResult:
    """config 生成 → url_check → 清理。

    - 调 engine.build_outbound_config 生成 config 写到 /tmp
    - 内部从 settings 读 test_url / curl_timeout，生成 tag
    - 调 checker.url_check
    - 清理临时文件
    """
```

## 依赖关系

```
checker.py   ← stdlib only (socket, subprocess, json, time, ...)
__init__.py  ← checker.py + engine + models.setting + settings
```

`checker.py` 是最底层，不含任何项目内部依赖。`__init__.py` 在它之上做 settings 读取和 config 生成。

## 文件变更

| 文件 | 内容 |
|------|------|
| `app/checker/__init__.py` | check_node + _check_url_one |
| `app/checker/checker.py` | CheckResult + allocate_ports + tcp_check + url_check |

## 验证

```bash
# 底层纯函数（不需要 Flask app context）
python3 -c "from app.checker.checker import tcp_check; tcp_check('1.2.3.4', 443, 1)"

# 完整链路
python3 test/test_checker.py
```
