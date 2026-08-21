"""Flask routes — CRUD + sing-box lifecycle + service control + upgrade.

Blueprint ``api`` with /api/* endpoints. No auth yet (deferred to the Web
layer per docs/design.md §2). Each handler is a thin translation layer:
extract params → call db/service → format JSON response.
"""

from flask import Blueprint, jsonify, request

from app import services
from app import settings
from app.db import subscription as db_sub
from app.db import node as db_node
from app.db import inbound as db_inbound
from app.db import outbound as db_outbound
from app.db import service as db_service
from app.singbox import upgrade

bp = Blueprint('api', __name__)


# ---------------------------------------------------------------------------
# sing-box process control (existing)
# ---------------------------------------------------------------------------

@bp.route('/api/status', methods=['GET'])
def api_status():
    return jsonify(services.get_status())


@bp.route('/api/start', methods=['POST'])
def api_start():
    r = services.start_singbox()
    return jsonify(r), 200 if r['success'] else 500


@bp.route('/api/stop', methods=['POST'])
def api_stop():
    r = services.stop_singbox()
    return jsonify(r), 200 if r['success'] else 500


@bp.route('/api/restart', methods=['POST'])
def api_restart():
    r = services.restart_singbox()
    return jsonify(r), 200 if r['success'] else 500


# ---------------------------------------------------------------------------
# Subscriptions CRUD
# ---------------------------------------------------------------------------

@bp.route('/api/subscriptions', methods=['GET'])
def list_subscriptions():
    return jsonify({'subscriptions': [dict(r) for r in db_sub.list_all() if r['id'] > 0]})


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


# ---------------------------------------------------------------------------
# Nodes CRUD
# ---------------------------------------------------------------------------

@bp.route('/api/nodes', methods=['GET'])
def list_nodes():
    return jsonify({'nodes': [dict(r) for r in db_node.list_all()]})


@bp.route('/api/nodes/grouped', methods=['GET'])
def list_nodes_grouped():
    groups = []
    for g in db_node.list_grouped():
        groups.append({
            'sub': dict(g['sub']) if g['sub'] else None,
            'nodes': [dict(n) for n in g['nodes']],
        })
    return jsonify({'groups': groups})


@bp.route('/api/nodes/by-sub/<int:sub_id>', methods=['GET'])
def list_nodes_by_sub(sub_id):
    return jsonify({'nodes': [dict(r) for r in db_node.list_by_sub(sub_id)]})


@bp.route('/api/nodes', methods=['POST'])
def create_node():
    d = request.get_json(force=True)
    nid = db_node.create(
        sub_id=d.get('sub_id', 0), name=d['name'], protocol=d['protocol'],
        address=d['address'], port=d['port'], config_json=d['config_json'])
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


# ---------------------------------------------------------------------------
# Inbounds CRUD
# ---------------------------------------------------------------------------

@bp.route('/api/inbounds', methods=['GET'])
def list_inbounds():
    return jsonify({'inbounds': [dict(r) for r in db_inbound.list_all()]})


@bp.route('/api/inbounds', methods=['POST'])
def create_inbound():
    d = request.get_json(force=True)
    iid = db_inbound.create(
        name=d['name'], protocol=d['protocol'],
        listen_addr=d.get('listen_addr', '0.0.0.0'),
        port=d['port'], params_json=d.get('params_json', '{}'))
    return jsonify({'success': True, 'id': iid}), 201


@bp.route('/api/inbounds/<int:in_id>', methods=['PUT'])
def update_inbound(in_id):
    d = request.get_json(force=True)
    db_inbound.update(in_id, **d)
    return jsonify({'success': True})


@bp.route('/api/inbounds/<int:in_id>', methods=['DELETE'])
def delete_inbound(in_id):
    db_inbound.delete(in_id)
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Outbounds CRUD
# ---------------------------------------------------------------------------

@bp.route('/api/outbounds', methods=['GET'])
def list_outbounds():
    result = []
    for r in db_outbound.list_all():
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


@bp.route('/api/outbounds/<int:out_id>', methods=['PUT'])
def update_outbound(out_id):
    d = request.get_json(force=True)
    db_outbound.update(out_id, **d)
    return jsonify({'success': True})


@bp.route('/api/outbounds/<int:out_id>', methods=['DELETE'])
def delete_outbound(out_id):
    if out_id == 0:
        return jsonify({'success': False, 'message': 'Cannot delete sentinel'}), 400
    db_outbound.delete(out_id)
    return jsonify({'success': True})


@bp.route('/api/outbounds/<int:out_id>/nodes', methods=['GET'])
def get_pool_nodes(out_id):
    return jsonify({'nodes': [dict(e) for e in db_outbound.get_pool_nodes(out_id)]})


@bp.route('/api/outbounds/<int:out_id>/nodes', methods=['POST'])
def add_pool_node(out_id):
    d = request.get_json(force=True)
    pid = db_outbound.add_pool_node(out_id, d['node_id'], d.get('priority'))
    return jsonify({'success': True, 'id': pid}), 201


@bp.route('/api/outbounds/<int:out_id>/nodes/<int:pool_id>', methods=['DELETE'])
def remove_pool_node(out_id, pool_id):
    db_outbound.remove_pool_node(pool_id)
    return jsonify({'success': True})


@bp.route('/api/outbounds/<int:out_id>/nodes/reorder', methods=['POST'])
def reorder_pool_nodes(out_id):
    d = request.get_json(force=True)
    db_outbound.sync_pool_nodes(out_id, d['node_ids'])
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Services CRUD + selector control
# ---------------------------------------------------------------------------

@bp.route('/api/services', methods=['GET'])
def list_services():
    return jsonify({'services': [dict(r) for r in db_service.list_all()]})


@bp.route('/api/services', methods=['POST'])
def create_service():
    d = request.get_json(force=True)
    sid = db_service.create(
        name=d['name'], inbound_id=d['inbound_id'],
        outbound_id=d['outbound_id'], auto_start=d.get('auto_start', 0))
    return jsonify({'success': True, 'id': sid}), 201


@bp.route('/api/services/<int:svc_id>', methods=['PUT'])
def update_service(svc_id):
    d = request.get_json(force=True)
    db_service.update(svc_id, **d)
    return jsonify({'success': True})


@bp.route('/api/services/<int:svc_id>', methods=['DELETE'])
def delete_service(svc_id):
    db_service.delete(svc_id)
    return jsonify({'success': True})


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


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@bp.route('/api/settings', methods=['GET'])
def get_settings():
    s = settings.get_all_settings()
    if s.get('web_password'):
        s['web_password'] = '******'
    return jsonify({'settings': s})


@bp.route('/api/settings', methods=['POST'])
def update_settings():
    d = request.get_json(force=True)
    if d.get('web_password') == '******':
        d.pop('web_password')
    settings.update_settings(d)
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

@bp.route('/api/upgrade/status', methods=['GET'])
def upgrade_status():
    r = upgrade.check_upgrade()
    if not r['success']:
        return jsonify(r), 502
    return jsonify(r)


@bp.route('/api/upgrade/download', methods=['POST'])
def upgrade_download():
    r = upgrade.download_upgrade()
    if not r['success']:
        return jsonify(r), 502
    return jsonify(r)
