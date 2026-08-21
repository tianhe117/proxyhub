# Service 级 API 设计（启停/切节点）

> 层级：服务层 + 路由层。承接 [设计文档](design.md) §5 服务状态模型。
> 状态：⏳ 待确认。

## 1. 背景

v2 架构下"启停服务"不再是起停进程（sing-box 是单常驻进程），而是**切 selector**（[设计文档](design.md) §5）：

| 状态 | 含义 | 实现 |
|------|------|------|
| run | 服务在代理 | selector `g{id}` 的 `now` 指向真实节点 `n{id}` |
| stop | 服务不代理 | selector `g{id}` 的 `now` 指向 `direct` |

因此 start/stop/restart **统一为 `PUT /proxies/{g{id}}`** 这一个操作，只是切到的目标不同：
- start service → 切到默认节点（pool priority 最小）
- stop service → 切到 `direct`
- restart service → stop + start

与 `/api/start`（起 sing-box 进程）完全不同——那是全局进程控制，这是单个 service 的路由控制。

## 2. DB 层前置

service 表结构（[db/service.py](../app/db/service.py)）：
```sql
services (
    id, name, inbound_id, outbound_id, auto_start
)
```

`outbound_id` 关联 `outbounds` 表 → `outbound_nodes` 表 → `nodes` 表。

已有函数：
- `db_service.get_by_id(svc_id)` → service 行
- `db_outbound.get_pool_nodes(outbound_id)` → 池子（含 node_id + priority + node 详情）
- `clash.select_proxy(group_tag, node_tag)` → 切 selector
- `clash.get_proxy_now(group_tag)` → 查当前选中

## 3. 服务层接口

在 `app/services.py` 中追加：

```python
def start_service(svc_id):
    """Route traffic through this service's selector.

    1. 读 service → outbound → pool
    2. pool 为空 → error
    3. 取 pool[0]（priority 最小）的 node tag
    4. clash.select_proxy(g{outbound_id}, n{node_id})
    5. 返回 {success, message, node_tag}
    """

def stop_service(svc_id):
    """Stop routing: switch this service's selector to direct.

    1. 读 service → outbound_id
    2. outbound_id == 0 → 已是 direct，success
    3. clash.select_proxy(g{outbound_id}, direct)
    4. 返回 {success, message}
    """

def restart_service(svc_id):
    """Stop then start (re-select default node)."""

def get_service_status(svc_id):
    """Query clash_api for this service's selector current node.

    1. 读 service → outbound_id
    2. outbound_id == 0 → {status: 'direct'}
    3. clash.get_proxy_now(g{outbound_id}) → 当前 node tag
    4. 返回 {status: 'running'|'stopped', current_node: 'n{id}'|'direct'}
    """
```

### 3.1 start_service 详细流程

```python
def start_service(svc_id):
    svc = db_service.get_by_id(svc_id)
    if not svc:
        return {'success': False, 'message': 'Service not found'}
    oid = svc['outbound_id']
    if oid == 0:
        return {'success': False, 'message': 'direct outbound cannot be started'}

    pool = db_outbound.get_pool_nodes(oid)
    if not pool:
        return {'success': False, 'message': 'Outbound pool is empty'}

    # pool 已按 priority ASC 排序
    default_node_id = pool[0]['node_id']
    node_tag = f'n{default_node_id}'
    group_tag = f'g{oid}'

    ok = clash.select_proxy(group_tag, node_tag)
    if ok:
        log.info(f'service "{svc["name"]}" started → {node_tag}')
        return {'success': True, 'message': f'Started → {node_tag}',
                'node_tag': node_tag}
    log.error(f'service "{svc["name"]}" start failed: clash_api error')
    return {'success': False, 'message': 'clash_api selector switch failed'}
```

### 3.2 stop_service 详细流程

```python
def stop_service(svc_id):
    svc = db_service.get_by_id(svc_id)
    if not svc:
        return {'success': False, 'message': 'Service not found'}
    oid = svc['outbound_id']
    if oid == 0:
        return {'success': True, 'message': 'Already direct'}
    group_tag = f'g{oid}'
    ok = clash.select_proxy(group_tag, 'direct')
    if ok:
        log.info(f'service "{svc["name"]}" stopped → direct')
        return {'success': True, 'message': 'Stopped → direct'}
    return {'success': False, 'message': 'clash_api selector switch failed'}
```

### 3.3 切换到指定节点（手动选节点）

v1 无此接口但 v2 clash_api 天然支持。给前端"手动切节点"留口：

```python
def switch_node(svc_id, node_id):
    """Manually switch this service's selector to a specific node.

    验证 node_id 在该 outbound 的 pool 中。
    """
```

路由：`POST /api/services/<id>/switch` body: `{node_id: int}`。

## 4. 路由层

| 方法 | 路径 | 处理函数 | 实现 |
|------|------|---------|------|
| POST | `/api/services/<int:id>/start` | `api_start_service` | `services.start_service(id)` |
| POST | `/api/services/<int:id>/stop` | `api_stop_service` | `services.stop_service(id)` |
| POST | `/api/services/<int:id>/restart` | `api_restart_service` | `services.restart_service(id)` |
| POST | `/api/services/<int:id>/switch` | `api_switch_node` | body: `{node_id}` → `services.switch_node(id, node_id)` |
| GET | `/api/services/<int:id>/status` | `api_service_status` | `services.get_service_status(id)` |

```python
@bp.route('/api/services/<int:svc_id>/start', methods=['POST'])
def api_start_service(svc_id):
    r = services.start_service(svc_id)
    return jsonify(r), 200 if r['success'] else 400

@bp.route('/api/services/<int:svc_id>/stop', methods=['POST'])
def api_stop_service(svc_id):
    r = services.stop_service(svc_id)
    return jsonify(r), 200 if r['success'] else 400

@bp.route('/api/services/<int:svc_id>/restart', methods=['POST'])
def api_restart_service(svc_id):
    r = services.restart_service(svc_id)
    return jsonify(r), 200 if r['success'] else 400

@bp.route('/api/services/<int:svc_id>/switch', methods=['POST'])
def api_switch_node(svc_id):
    d = request.get_json(force=True)
    r = services.switch_node(svc_id, d['node_id'])
    return jsonify(r), 200 if r['success'] else 400

@bp.route('/api/services/<int:svc_id>/status', methods=['GET'])
def api_service_status(svc_id):
    return jsonify(services.get_service_status(svc_id))
```

## 5. 关键决策

| 决策 | 内容 | 理由 |
|------|------|------|
| start = 切 selector | 不起停进程 | design.md §5 核心决策，sing-box 单进程 |
| stop = 切到 `direct` | 非 `block` | 与 v1 `outbound_id=0` 语义一致，直连不丢包 |
| 默认节点 = pool[0] | priority ASC 取第一个 | 无需额外配置，pool 顺序即优先级 |
| pool 为空拒绝 start | 无节点可选 | 前端提示用户先添加节点 |
| switch_node 需验证 | node_id 必须在 pool 中 | 防止切到不属于该 outbound 的节点 |

## 6. 验证

1. 创建 service（inbound=socks, outbound=g15）→ `POST /api/services/1/start` → `get_proxy_now('g15')` 返回 `n{id}`
2. `POST /api/services/1/stop` → `get_proxy_now('g15')` 返回 `direct`
3. `POST /api/services/1/switch` body `{node_id: 1126}` → `get_proxy_now('g15')` 返回 `n1126`
4. `GET /api/services/1/status` → `{status: 'running', current_node: 'n1126'}`
