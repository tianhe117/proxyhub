# proxy_url_check.sh 重构设计

## 目标

`proxy_url_check.sh` 专注 URL 代理可达性测试，去掉 Python 依赖，纯 bash 实现。

## 现状问题

```
script.py
├── tcp_ping()  →  bash test.sh tcp_ping  →  shell 调 python -c 做 socket  →  shell 调 python -c 输出 JSON
└── url_test()  →  bash test.sh url_test  →  启动代理 → 等端口 → curl → 清理进程 → 输出 JSON
```

- `tcp_ping` 绕了三层（Python→bash→Python→bash→Python），无进程管理需求却承受 subprocess 开销
- stdin JSON 被 python -c 解析 **7 次**（config_path、bin_type、bin_path、local_port、test_url、curl_timeout、tag 各一次）
- `json_err` 字符串拼接进 Python 源码，含单引号时 SyntaxError
- 多处 `local` 与命令替换组合掩盖退出码
- `except:` 裸捕获吞掉 KeyboardInterrupt/SysExit

## 目标形态

```
script.py
├── tcp_ping()  →  纯 Python socket（~15 行，零 subprocess）
└── url_test()  →  bash test.sh（纯 bash，零 Python 依赖）
```

## test.sh 重构细节

### 1. 接口：stdin JSON → CLI 参数

```
旧：echo '{"config_path":"...","bin_type":"xray",...}' | ./test.sh url_test
新：./test.sh <config> <bin_type> <bin_path> <port> <test_url> <timeout> <tag>
```

`script.py` 负责把 dict 展开为参数传入，不再 json.dumps。

### 2. Python 依赖：全部移除

| 当前用途 | 替代方案 |
|---------|---------|
| `json.dump` 输出 JSON | `printf` 直接拼，数字字段无需转义 |
| `json.load(sys.stdin)` 解析输入 | CLI 参数，无需解析 |
| `json_err` 的错误消息转义 | bash 内置替换 `"//\"/\\\"` |
| `wait_for_port` socket 探测 | `bash /dev/tcp` 或 `nc -z` |
| `tcp_ping` socket connect | 移到 `script.py` 纯 Python 实现 |

### 3. JSON 输出

```bash
# 成功
printf '{"success":true,"http_code":%d,"latency_ms":%d}\n' "$http_code" "$elapsed_ms"

# 失败（错误消息需转义双引号）
err_msg="${1//\"/\\\"}"
printf '{"success":false,"error":"%s"}\n' "$err_msg"
```

### 4. 端口等待

```bash
wait_for_port() {
    local port="$1" max="${2:-15}"
    local i=0
    while [ $i -lt $max ]; do
        timeout 1 bash -c "echo >/dev/tcp/127.0.0.1/$port" 2>/dev/null && return 0
        sleep 0.5
        i=$((i + 1))
    done
    return 1
}
```

`/dev/tcp` 是 bash 内建特性（编译期开启，Alpine/Ubuntu 默认支持），不走用户态 socket 调用。

### 5. 进程清理

保留三层清理（PGID → tag → config），去掉 `local` 掩盖退出码的问题：

```bash
cleanup_process_tree() {
    local pid_file="$1" tag="$2" config_path="$3"
    local pid pgid matched config_file

    # Layer 1: kill process group by PGID
    ...
    # Layer 2: pgrep by tag
    ...
    # Layer 3: pgrep by config filename
    ...
    rm -f "$pid_file" "$config_path"
}
```

所有命令结果先赋值（变量声明与赋值分离），再检查结果。

### 6. curl 重试逻辑

保持现有 3 次重试、HTTP 000 快速重试逻辑不变。只用 bash 变量和算术运算：

```bash
local max_attempts=3 retry_delay=1 attempt http_code elapsed_ms start_ns end_ns
start_ns=$(date +%s%N)

for attempt in $(seq 1 $max_attempts); do
    http_code=$(curl ...)
    [ "$http_code" = "204" ] && break

    elapsed_ms=$(( ($(date +%s%N) - start_ns) / 1000000 ))
    if [ "$http_code" = "000" ] && [ "$elapsed_ms" -lt 2000 ]; then
        [ "$attempt" -lt "$max_attempts" ] && sleep "$retry_delay"
    else
        break
    fi
done
```

## script.py 重构细节

### tcp_ping 改为纯 Python

```python
import socket
import time

def tcp_ping(address, port, timeout, tag):
    try:
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((address, int(port)))
        latency = round((time.time() - start) * 1000)
        sock.close()
        return {'success': True, 'latency_ms': latency}
    except Exception as e:
        return {'success': False, 'error': str(e)}
```

不再调用 subprocess，约 15 行。—— `tag` 参数保留以兼容调用方接口。

### url_test 参数传递改为 CLI args

```python
def url_test(config_path, bin_type, bin_path, local_port, test_url, curl_timeout, tag):
    script = _get_script_path()
    try:
        result = subprocess.run(
            ['bash', script,
             config_path, bin_type, bin_path,
             str(local_port), test_url, str(curl_timeout), tag],
            capture_output=True, text=True,
            timeout=curl_timeout + 30,
        )
        ...
```

## 调用方影响

`checker/__init__.py` 和 `service_manager.py` 中的 `tcp_ping()` / `url_test()` 调用保持参数不变，**零改动**。

## 收缩后 test.sh 结构

```
~80 行，结构：
├── 注解头 + set -euo pipefail
├── json_ok()      — printf JSON 成功输出
├── json_err()     — printf JSON 错误输出（转义双引号）
├── wait_for_port()    — /dev/tcp 端口等待
├── cleanup_process_tree() — 三层进程清理
├── main (url_test) — 串起整个流程
└── 不再需要 case dispatch
```

因为只做 URL 测试一件事，dispatch 可以直接去掉，脚本退化为单一功能入口。
