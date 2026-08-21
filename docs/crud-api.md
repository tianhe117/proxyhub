# CRUD API 路由设计

> 层级：Web/路由层。承接 [顶层设计](design.md) §4 路由设计 + [routes.md](routes.md) 的蓝图结构。
> 状态：⏳ 待确认。

## 1. 背景

DB 层全部就绪（[app/db/](../app/db/)），routes.py 已有进程控制蓝图（`/api/start|stop|restart|status`），但节点/订阅/入站/出站/服务/设置的 CRUD 路由未写。本轮实现纯翻译层——提取参数 → 调 db.* → 返回 JSON，不超过 10 行/函数。

不做前端模板，不做认证，不做服务启停（归 service-level API，见 [service-api.md](service-api.md)）。

## 2. 路由设计准则

承 v1 §8.1：
- **每个路由处理函数不超过 10 行**
- 只做：参数提取 → 调用 db → 格式化返回
- 不做：数据库操作、业务判断、配置生成、进程管理
- `sqlite3.Row` 返回时转 `dict(row)` 前端可用
- 统一 `jsonify({success, ...})` 格式（承 [routes.md](routes.md)）

## 3. 订阅路由（Blueprint: `api`，已有）

| 方法 | 路径 | 处理函数 | 实现 |
|------|------|---------|------|
| GET | `/api/subscriptions` | `list_subscriptions` | `db_sub.list_all()` → 跳过 id=0 哨兵 → 列表 |
| POST | `/api/subscriptions` | `create_subscription` | body: `{name, url, filter_keywords?, exclude_keywords?}` → `db_sub.create(...)` |
| PUT | `/api/subscriptions/<int:id>` | `update_subscription` | body: 部分字段 → `db_sub.update(id, **fields)` |
| DELETE | `/api/subscriptions/<int:id>` | `delete_subscription` | `db_sub.delete(id)`，id=0 拒绝 |
| POST | `/api/subscriptions/<int:id>/refresh` | `refresh_subscription` | `services.refresh_subscription(id)` |

```python
@bp.route('/api/subscriptions', methods=['GET'])
def list_subscriptions():
    rows = db_sub.list_all()
    return jsonify({'subscriptions': [dict(r) for r in rows if r['id'] > 0]})

@bp.route('/api/subscriptions', methods=['POST'])
def create_subscription():
    d = request.get_json(force=True)
    sid = db_sub.create(d['name'], d['url'],
                        d.get('filter_keywords', ''), d.get('exclude_keywords', ''))
    return jsonify({'success': True, 'id': sid}), 201

@bp.route('/api/subscriptions/<int:sub_id>', methods=['PUT'])
def update_subscription(sub_id):
    d = request.get_json(force=True)
    db_sub.update(sub_id, **d)
    return jsonify({'success': True})

@bp.route('/api/subscriptions/<int:sub_id>', methods=['DELETE'])
def delete_subscription(sub_id):
    if sub_id == 0:
        return jsonify({'success': False, 'message': 'Cannot delete sentinel'}), 400
    db_sub.delete(sub_id)
    return jsonify({'success': True})

@bp.route('/api/subscriptions/<int:sub_id>/refresh', methods=['POST'])
def refresh_subscription(sub_id):
    return jsonify(services.refresh_subscription(sub_id))
```

## 4. 节点路由

| 方法 | 路径 | 处理函数 | 实现 |
|------|------|---------|------|
| GET | `/api/nodes` | `list_nodes` | `db_node.list_all()` → 全量 |
| GET | `/api/nodes/grouped` | `list_nodes_grouped` | `db_node.list_grouped()` → 按订阅分组 |
| GET | `/api/nodes/by-sub/<int:sub_id>` | `list_nodes_by_sub` | `db_node.list_by_sub(sub_id)` |
| POST | `/api/nodes` | `create_node` | body: `{sub_id?, name, protocol, address, port, config_json}` → `db_node.create(...)` |
| PUT | `/api/nodes/<int:id>` | `update_node` | body: 部分字段 → `db_node.update(id, **fields)` |
| DELETE | `/api/nodes/<int:id>` | `delete_node` | `db_node.delete(id)` |
| POST | `/api/nodes/clear` | `clear_nodes` | `db_node.delete_all()` |

```python
@bp.route('/api/nodes', methods=['GET'])
def list_nodes():
    return jsonify({'nodes': [dict(r) for r in db_node.list_all()]})

@bp.route('/api/nodes/grouped', methods=['GET'])
def list_nodes_grouped():
    groups = db_node.list_grouped()
    result = []
    for g in groups:
        result.append({
            'sub': dict(g['sub']) if g['sub'] else None,
            'nodes': [dict(n) for n in g['nodes']],
        })
    return jsonify({'groups': result})

@bp.route('/api/nodes', methods=['POST'])
def create_node():
    d = request.get_json(force=True)
    nid = db_node.create(
        sub_id=d.get('sub_id', 0),
        name=d['name'], protocol=d['protocol'],
        address=d['address'], port=d['port'],
        config_json=d['config_json'])
    return jsonify({'success': True, 'id': nid}), 201

@bp.route('/api/nodes/<int:node_id>', methods=['PUT'])
def update_node(node_id):
    d = request.get_json(force=True)
    db_node.update(node_id, **d)
    return jsonify({'success': True})

@bp.route('/api/nodes/<int:node_id>', methods=['DELETE'])
def delete_node(node_id):
    db_node.delete(node_id)
    return jsonify({'success': True})

@bp.route('/api/nodes/clear', methods=['POST'])
def clear_nodes():
    db_node.delete_all()
    return jsonify({'success': True})
```

## 5. 入站路由

| 方法 | 路径 | 处理函数 | 实现 |
|------|------|---------|------|
| GET | `/api/inbounds` | `list_inbounds` | `db_inbound.list_all()` |
| POST | `/api/inbounds` | `create_inbound` | body: `{name, protocol, listen_addr?, port, params_json?}` → `db_inbound.create(...)` |
| PUT | `/api/inbounds/<int:id>` | `update_inbound` | body: 部分字段 → `db_inbound.update(id, **fields)` |
| DELETE | `/api/inbounds/<int:id>` | `delete_inbound` | `db_inbound.delete(id)` |

## 6. 出站路由

| 方法 | 路径 | 处理函数 | 实现 |
|------|------|---------|------|
| GET | `/api/outbounds` | `list_outbounds` | `db_outbound.list_all()` → 跳过 id=0 哨兵 |
| POST | `/api/outbounds` | `create_outbound` | body: `{name}` → `db_outbound.create(name)` |
| PUT | `/api/outbounds/<int:id>` | `update_outbound` | body: `{name}` → `db_outbound.update(id, **fields)` |
| DELETE | `/api/outbounds/<int:id>` | `delete_outbound` | id=0 拒绝 → `db_outbound.delete(id)` |
| GET | `/api/outbounds/<int:id>/nodes` | `get_pool_nodes` | `db_outbound.get_pool_nodes(id)` |
| POST | `/api/outbounds/<int:id>/nodes` | `add_pool_node` | body: `{node_id, priority?}` → `db_outbound.add_pool_node(...)` |
| DELETE | `/api/outbounds/<int:id>/nodes/<int:pool_id>` | `remove_pool_node` | `db_outbound.remove_pool_node(pool_id)` |
| POST | `/api/outbounds/<int:id>/nodes/reorder` | `reorder_pool_nodes` | body: `{node_ids: [...]}` → `db_outbound.sync_pool_nodes(id, node_ids)` |

```python
@bp.route('/api/outbounds', methods=['GET'])
def list_outbounds():
    rows = db_outbound.list_all()
    result = []
    for r in rows:
        if r['id'] == 0:
            continue
        d = dict(r)
        d['pool'] = [dict(e) for e in db_outbound.get_pool_nodes(r['id'])]
        result.append(d)
    return jsonify({'outbounds': result})

@bp.route('/api/outbounds', methods=['POST'])
def create_outbound():
    d = request.get_json(force=True)
    oid = db_outbound.create(d['name'])
    return jsonify({'success': True, 'id': oid}), 201

@bp.route('/api/outbounds/<int:out_id>/nodes', methods=['POST'])
def add_pool_node(out_id):
    d = request.get_json(force=True)
    pid = db_outbound.add_pool_node(out_id, d['node_id'], d.get('priority'))
    return jsonify({'success': True, 'id': pid}), 201

@bp.route('/api/outbounds/<int:out_id>/nodes/reorder', methods=['POST'])
def reorder_pool_nodes(out_id):
    d = request.get_json(force=True)
    db_outbound.sync_pool_nodes(out_id, d['node_ids'])
    return jsonify({'success': True})
```

## 7. 服务路由

| 方法 | 路径 | 处理函数 | 实现 |
|------|------|---------|------|
| GET | `/api/services` | `list_services` | `db_service.list_all()` |
| POST | `/api/services` | `create_service` | body: `{name, inbound_id, outbound_id, auto_start?}` → `db_service.create(...)` |
| PUT | `/api/services/<int:id>` | `update_service` | body: 部分字段 → `db_service.update(id, **fields)` |
| DELETE | `/api/services/<int:id>` | `delete_service` | `db_service.delete(id)` |

> service 的 start/stop/restart 归 [service-api.md](service-api.md)。

## 8. 设置路由

| 方法 | 路径 | 处理函数 | 实现 |
|------|------|---------|------|
| GET | `/api/settings` | `get_settings` | `settings.get_all_settings()`，密码脱敏 |
| POST | `/api/settings` | `update_settings` | body: `{key: value, ...}` → `settings.update_settings(updates)` |

```python
@bp.route('/api/settings', methods=['GET'])
def get_settings():
    s = settings.get_all_settings()
    if s.get('web_password'):
        s['web_password'] = '******'  # 脱敏
    return jsonify({'settings': s})

@bp.route('/api/settings', methods=['POST'])
def update_settings():
    d = request.get_json(force=True)
    if d.get('web_password') == '******':
        d.pop('web_password')  # 未修改，不更新
    settings.update_settings(d)
    return jsonify({'success': True})
```

## 9. 实现要点

- **全部路由注册在现有 `bp = Blueprint('api', __name__)`**，不新建 Blueprint
- `sqlite3.Row` → `dict(r)` 在路由层做（DB 层返回原始 Row）
- 返回码：创建 201，删除/更新 200，参数错误 400，不存在 404
- `request.get_json(force=True)` 忽略 Content-Type，方便调试
- 不做认证——等 [design.md](design.md) §2 核心决策再加 `auth_required` 装饰器

## 10. 验证

1. import 链：`from app import create_app; app = create_app(); print(app.url_map)` → 路由全注册
2. curl 测试各 CRUD（启动 Flask dev server）
3. 现有测试不回归
