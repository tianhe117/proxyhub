# 节点测试（checker）设计

> 层级：健康检查层。承接 [routes.md](routes.md) §3.6 CheckResult 定义 + [singbox/clash.py](../app/singbox/clash.py) 的 `get_delay`。
> 状态：⏳ 待确认。

## 1. 背景

手动测试节点延迟是开发/运维的基础能力。v2 两段式检查（TCP 预筛 + clash_api `/delay`），需支持单点/批量测试，批量时前端实时显示每个节点完成的结果（不等全部完成）。

## 2. 测试流程

```
POST /api/nodes/check
  │
  ├─ 1. 前置：确保 sing-box 运行 + config 包含待测节点
  │     ├─ sing-box 未运行 → apply_config + start
  │     └─ sing-box 已运行 → apply_config + restart
  │
  ├─ 2. 确定节点列表
  │     ├─ {node_id: N}         → 单点
  │     ├─ {node_ids: [...]}    → 指定批量
  │     ├─ {sub_id: N}          → 该订阅下所有节点
  │     └─ {}                   → 全量
  │
  └─ 3. 并发测试（ThreadPoolExecutor）
        └─ 每个节点: TCP → URL → CheckResult → 写 latency store + task dict
```

## 3. API 设计

### 3.1 POST `/api/nodes/check` — 发起测试

**请求体：**
```json
{"node_id": 42}                    // 单点，同步返回
{"node_ids": [42, 43, 44]}        // 批量，异步返回 task_id
{"sub_id": 5}                     // 某订阅下所有节点
{}                                 // 全量
```

**单点返回（同步，~1-5 秒）：**
```json
{
  "single": true,
  "node_id": 42,
  "result": {"tcp_latency_ms": 45, "url_latency_ms": 234, "error": ""}
}
```

**批量返回（异步，立即返回）：**
```json
{"task_id": "chk_1724150000_abc", "total": 28, "status": "running"}
```

### 3.2 GET `/api/nodes/check/<task_id>` — 查询进度（轮询）

前端每 1 秒轮询此端点，**每次拿到已完成的结果逐个渲染**：

```json
{
  "task_id": "chk_1724150000_abc",
  "status": "running",
  "total": 28,
  "completed": 12,
  "results": {
    "42": {"tcp_latency_ms": 45,  "url_latency_ms": 234, "error": ""},
    "43": {"tcp_latency_ms": -1,  "url_latency_ms": -1,  "error": "tcp: timeout"},
    "44": {"tcp_latency_ms": 120, "url_latency_ms": -1,  "error": "url: dial tcp: i/o timeout"}
  }
}
```

- `results` 包含**所有已完成节点**（包括本轮轮询新增的）
- `status: "running"` → 还有节点在测，继续轮询
- `status: "done"` → 全部完成，停止轮询，`results` 包含所有节点

**前端实时显示逻辑：**
```javascript
async function pollCheck(taskId, total) {
  const displayed = new Set();
  while (true) {
    const r = await fetch(`/api/nodes/check/${taskId}`);
    const data = await r.json();
    // 逐个渲染新完成的节点
    for (const [nodeId, result] of Object.entries(data.results)) {
      if (!displayed.has(nodeId)) {
        displayed.add(nodeId);
        renderLatency(nodeId, result);  // 更新该行延迟显示
      }
    }
    updateProgress(displayed.size, data.total);  // 进度条: 12/28
    if (data.status === 'done') break;
    await new Promise(ok => setTimeout(ok, 1000));
  }
}
```

每个节点测完就立即出现在页面上，**不需要等全部完成**。

### 3.3 GET `/api/nodes/<id>/latency` — 查单个节点最新结果

读内存 latency store（`get_latency(node_id)`），不做实际测试。

```json
{"node_id": 42, "latency": {"tcp_latency_ms": 45, "url_latency_ms": 234, "error": ""}}
```

节点从未测过时 `latency: null`（前端显示"—"）。

## 4. 内部实现

### 4.1 `app/checker.py`（新文件，扁平）

```python
"""Node health checker: TCP + clash_api URL test.

Single-node: check_node(node_id, address, port) → CheckResult
Batch:       check_nodes_async(node_list, task_id) → writes to _tasks

Both write results to the in-memory latency store (app.utils).
"""

import socket
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.utils import CheckResult, update_latency, log
from app.singbox.clash import get_delay
from app.settings import get_setting

MAX_WORKERS = 10

# Task store — batch test progress, keyed by task_id
_tasks = {}        # {task_id: {status, total, completed, results}}
_tasks_lock = threading.Lock()


def check_node(node_id, address, port):
    """Test a single node: TCP → URL → CheckResult → write latency store.

    Returns CheckResult.
    """
    tcp_timeout = int(get_setting('tcp_timeout'))
    tcp_ms = _tcp_check(address, port, tcp_timeout)
    if tcp_ms < 0:
        result = CheckResult(
            tcp_latency_ms=-1, url_latency_ms=-1,
            error=f'tcp: timeout ({tcp_timeout}s)')
        update_latency(node_id, result)
        return result

    test_url = get_setting('test_url')
    url_timeout = int(get_setting('curl_timeout')) * 1000
    r = get_delay(f'n{node_id}', test_url, url_timeout)
    if 'delay' in r:
        result = CheckResult(tcp_latency_ms=tcp_ms, url_latency_ms=r['delay'], error='')
    else:
        result = CheckResult(
            tcp_latency_ms=tcp_ms, url_latency_ms=-1,
            error=f'url: {r.get("error", "unknown")}')
    update_latency(node_id, result)
    return result


def check_nodes_async(node_list, task_id):
    """Batch test with ThreadPoolExecutor. Results written to _tasks + latency store.

    Args:
        node_list: [(node_id, address, port), ...]
        task_id: unique identifier for this batch
    """
    _init_task(task_id, len(node_list))
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        for nid, addr, port in node_list:
            f = pool.submit(check_node, nid, addr, port)
            futures[f] = nid
        for f in as_completed(futures):
            nid = futures[f]
            try:
                result = f.result()
            except Exception as e:
                result = CheckResult(tcp_latency_ms=-1, url_latency_ms=-1, error=str(e))
                update_latency(nid, result)
            _update_task(task_id, nid, result)
    _finish_task(task_id)


def get_task(task_id):
    """Return task progress dict, or None if not found."""
    with _tasks_lock:
        return _tasks.get(task_id)


def _tcp_check(addr, port, timeout):
    """TCP handshake timing. Returns ms on success, -1 on failure."""
    try:
        start = time.monotonic()
        with socket.create_connection((addr, port), timeout=timeout):
            return int((time.monotonic() - start) * 1000)
    except (socket.timeout, OSError):
        return -1


def _init_task(task_id, total):
    with _tasks_lock:
        _tasks[task_id] = {
            'status': 'running',
            'total': total,
            'completed': 0,
            'results': {},
        }


def _update_task(task_id, node_id, result):
    with _tasks_lock:
        t = _tasks.get(task_id)
        if not t:
            return
        t['results'][str(node_id)] = {
            'tcp_latency_ms': result.tcp_latency_ms,
            'url_latency_ms': result.url_latency_ms,
            'error': result.error,
        }
        t['completed'] = len(t['results'])


def _finish_task(task_id):
    with _tasks_lock:
        t = _tasks.get(task_id)
        if t:
            t['status'] = 'done'
```

### 4.2 路由层（在 `app/routes.py` 追加）

```python
import uuid, time
from app import checker

@bp.route('/api/nodes/check', methods=['POST'])
def api_check_nodes():
    """发起节点测试。单点同步，批量异步。"""
    # 前置：确保 sing-box 运行且 config 包含待测节点
    if not sb_is_running():
        services.start_singbox()
    else:
        services.apply_config()
        sb_restart()

    d = request.get_json(force=True) if request.data else {}

    # 解析节点列表
    if 'node_id' in d:
        node_list = _resolve_nodes([d['node_id']])
    elif 'node_ids' in d:
        node_list = _resolve_nodes(d['node_ids'])
    elif 'sub_id' in d:
        node_list = _resolve_nodes_by_sub(d['sub_id'])
    else:
        node_list = _resolve_all_nodes()

    if not node_list:
        return jsonify({'success': False, 'message': 'No nodes to check'}), 400

    # 单点同步
    if len(node_list) == 1:
        nid, addr, port = node_list[0]
        result = checker.check_node(nid, addr, port)
        return jsonify({
            'single': True,
            'node_id': nid,
            'result': {
                'tcp_latency_ms': result.tcp_latency_ms,
                'url_latency_ms': result.url_latency_ms,
                'error': result.error,
            }
        })

    # 批量异步
    task_id = f'chk_{int(time.time())}_{uuid.uuid4().hex[:6]}'
    threading.Thread(
        target=checker.check_nodes_async,
        args=(node_list, task_id),
        daemon=True
    ).start()
    return jsonify({'task_id': task_id, 'total': len(node_list), 'status': 'running'})


@bp.route('/api/nodes/check/<task_id>', methods=['GET'])
def api_check_status(task_id):
    """查询批量测试进度。前端每秒轮询。"""
    task = checker.get_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)


@bp.route('/api/nodes/<int:node_id>/latency', methods=['GET'])
def api_node_latency(node_id):
    """查单个节点最新测试结果（内存 store）。"""
    from app.utils import get_latency
    r = get_latency(node_id)
    return jsonify({
        'node_id': node_id,
        'latency': {
            'tcp_latency_ms': r.tcp_latency_ms,
            'url_latency_ms': r.url_latency_ms,
            'error': r.error,
        } if r else None
    })
```

## 5. 并发与性能

| 维度 | 方案 | 理由 |
|------|------|------|
| 并发数 | `ThreadPoolExecutor(max_workers=10)` | socket 测试不吃 CPU，10 并发够用；clash_api 单进程不怕压 |
| TCP 测试 | 纯 Python socket，独立线程 | 不依赖 sing-box，可完全并行 |
| URL 测试 | 调 clash_api HTTP | sing-box 单进程 HTTP，10 并发足够 |
| task 存储 | 内存 dict + `_tasks_lock` | 测完前端拿到就行，重启丢弃无影响 |
| latency 存储 | 现有 `update_latency`（已有 `_lock`） | last-write-wins，线程安全 |

## 6. 前置步骤：apply_config + restart

每次 `POST /api/nodes/check` 前自动执行。理由：

- 新入库的节点不在当前 config → clash_api `GET /proxies/n{id}/delay` 返回 404
- `apply_config` 是纯函数 + 原子写，很快（<100ms）
- `restart` 约 0.5 秒，但只在 sing-box 已运行时需要

单点测试场景：前端点"测速"→ 自动 apply + restart → 测速 → 返回结果。用户无感。

## 7. 关键决策

| 决策 | 内容 | 理由 |
|------|------|------|
| 单点同步 | 不走 task_id，直接返回结果 | 1-5 秒等得起，不用轮询 |
| 批量异步 | task_id + 轮询 | 28 节点可能 2 分钟，不能阻塞 HTTP |
| 增量结果 | task dict 逐条写入，前端每秒轮询 | 每个节点测完立刻显示，不等全部完成 |
| task_id 格式 | `chk_{timestamp}_{random}` | 可读 + 不冲突 |
| daemon 线程 | `threading.Thread(daemon=True)` | 进程退出时自动清理，不阻塞 shutdown |
| apply_config 前置 | 每次 check 前自动刷新 | 确保新节点在 clash 里 |

## 8. 验证

1. `POST /api/nodes/check {"node_id": 983}` → 同步返回 `{tcp_latency_ms: N, url_latency_ms: M}`
2. `POST /api/nodes/check {"sub_id": 5}` → `{task_id: "chk_...", "total": 28}`
3. `GET /api/nodes/check/chk_...` → 轮询，`completed` 递增，`results` 逐条新增
4. `GET /api/nodes/983/latency` → 最新结果
5. sing-box 未运行时 POST → 自动 start → 测试正常
