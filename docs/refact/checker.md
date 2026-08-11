# checker 重写设计

## 目标

两层 API：底层纯函数不碰 DB，顶层 node_id 便捷入口。调用方按需选用。

## API

### 底层 — 纯数据驱动，无 DB 依赖

```python
# TCP 检测：连一下端口就完事
tcp_check(address: str, port: int, timeout: int = 3) -> CheckResult

# URL 检测：启代理 → curl → 杀进程
url_check(node: dict, port: int, test_url: str, timeout: int, tag: str) -> CheckResult
```

底层函数可直接用于：单元测试（构造 fake dict）、故障转移（已有 node dict 在内存）、脚本调用。

### 顶层 — node_id 便捷入口

```python
# 入参 int 或 list[int]，内部查 DB 后调底层
tcp_ping(node_ids: int | list[int], timeout: int = 3) -> dict[int, CheckResult]
url_test(node_ids: int | list[int], timeout: int = 6) -> dict[int, CheckResult]
```

顶层函数适用于批量健康检查，一行搞定。批量场景内部用 ThreadPoolExecutor 并发。

### 返回类型

```python
@dataclass
class CheckResult:
    success: bool
    latency_ms: int
    http_code: str     # tcp 检测时永远为 "0"
    error: str
```

返回 dict key 为 node_id。

### 适用场景

| 场景 | 用哪个 | 原因 |
|------|--------|------|
| 健康检查线程（`_run_checks`） | `url_test([id1, id2, ...])` | 批量并发，一行搞定 |
| 故障转移（`service_manager.py`） | `url_check(node, port, url, timeout, tag)` | node dict 已经在内存，不白查 DB |
| 单元测试 | `tcp_check("1.2.3.4", 443)` | 构造 fake dict 不依赖 DB |
| 命令行脚本 | `tcp_check("1.2.3.4", 443, 3)` | 不需要 node_id |

## 调用方代码变化

### checker/__init__.py（健康检查）

```python
# 旧 — 手动管理所有细节
for node in nodes:
    res = tcp_ping(node['address'], node['port'], tcp_timeout, tag)
    port = find_temp_port()
    config_path = generate_temp_config(node, port)
    res = url_test(config_path, bin_type, bin_path, port, test_url, timeout, tag)
    os.remove(config_path)

# 新 — 底层或顶层都行
# 方式 A：顶层，一行
results = url_test([n['id'] for n in nodes])

# 方式 B：底层，已有 node dict 在手
for node in nodes:
    tcp = tcp_check(node['address'], node['port'], tcp_timeout)
    url = url_check(node, port, test_url, curl_timeout, tag)
```

### service_manager.py（故障转移）

```python
# 旧
tcp_res = tcp_ping(node['address'], node['port'], tcp_timeout, tag)
port = find_temp_port()
config_path = generate_temp_config(node, port)
url_res = url_test(config_path, bin_type, bin_path, port, test_url, timeout, tag)
os.remove(config_path)

# 新 — 底层，node dict 在内存不查 DB
tcp_res = tcp_check(node['address'], node['port'], tcp_timeout)
url_res = url_check(node, port, test_url, curl_timeout, tag)
```

## 内部实现

### tcp_check

纯 Python socket connect，零 subprocess，零临时文件。

### url_check

单向流程：

1. 调 `build_outbound_config(node, port)` 生成 config dict
2. 写入 `/tmp/ph_check/<tag>.json`
3. subprocess 调 `proxy_url_check.sh`
4. 删掉 `/tmp/ph_check/<tag>.json`
5. 解析 stdout JSON 返回 CheckResult

### url_test（顶层批量）

1. `get_by_id()` 批量查 DB
2. `allocate_ports(n)` 一次拿够端口
3. ThreadPoolExecutor 并发调 `url_check()`

### 端口分配

50000-60000 顺序扫描，一次预分配全部。

### 代理二进制映射

```python
BIN_MAP = {
    'xray':     'bin/xray',
    'sslocal':  'bin/sslocal',
    'sing-box': 'bin/sing-box',
}
```

## 文件结构

```
app/checker/
├── __init__.py    # tcp_ping(), url_test() — 顶层 (node_id → DB → 底层)
├── tcp.py         # tcp_check() — 底层，纯 socket
├── url.py         # url_check() — 底层，subprocess 调 proxy_url_check.sh
├── port.py        # allocate_ports(n) → list[int]
└── config.py      # generate_config(node, port) → path
```

`script.py` 删除，逻辑内聚到各个模块。
