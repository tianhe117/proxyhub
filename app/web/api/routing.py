"""Inbound, outbound, and service routing API routes."""

from flask import jsonify, request

from app.db import inbound as db_inbound
from app.db import outbound as db_outbound
from app.db import service as db_service
from app.services.routing import (
    get_service_status,
    restart_service,
    start_service,
    stop_service,
    switch_node,
)
from app.singbox.clash import get_proxy_now
from app.web.api import bp


@bp.route('/api/inbounds', methods=['GET'])
def list_inbounds():
    return jsonify({'inbounds': [dict(row) for row in db_inbound.list_all()]})


@bp.route('/api/inbounds', methods=['POST'])
def create_inbound():
    data = request.get_json(force=True)
    inbound_id = db_inbound.create(
        name=data['name'],
        protocol=data['protocol'],
        listen_addr=data.get('listen_addr', '0.0.0.0'),
        port=data['port'],
        params_json=data.get('params_json', '{}'),
    )
    return jsonify({'success': True, 'id': inbound_id}), 201


@bp.route('/api/inbounds/<int:in_id>', methods=['PUT'])
def update_inbound(in_id):
    db_inbound.update(in_id, **request.get_json(force=True))
    return jsonify({'success': True})


@bp.route('/api/inbounds/<int:in_id>', methods=['DELETE'])
def delete_inbound(in_id):
    db_inbound.delete(in_id)
    return jsonify({'success': True})


@bp.route('/api/outbounds', methods=['GET'])
def list_outbounds():
    result = []
    for row in db_outbound.list_all():
        if row['id'] == 0:
            continue
        item = dict(row)
        item['pool'] = [dict(entry) for entry in db_outbound.get_pool_nodes(row['id'])]
        result.append(item)
    return jsonify({'outbounds': result})


@bp.route('/api/outbounds', methods=['POST'])
def create_outbound():
    outbound_id = db_outbound.create(request.get_json(force=True)['name'])
    return jsonify({'success': True, 'id': outbound_id}), 201


@bp.route('/api/outbounds/<int:out_id>', methods=['PUT'])
def update_outbound(out_id):
    db_outbound.update(out_id, **request.get_json(force=True))
    return jsonify({'success': True})


@bp.route('/api/outbounds/<int:out_id>', methods=['DELETE'])
def delete_outbound(out_id):
    if out_id == 0:
        return jsonify({'success': False, 'message': 'Cannot delete sentinel'}), 400
    db_outbound.delete(out_id)
    return jsonify({'success': True})


@bp.route('/api/outbounds/<int:out_id>/nodes', methods=['GET'])
def get_pool_nodes(out_id):
    return jsonify({'nodes': [dict(entry) for entry in db_outbound.get_pool_nodes(out_id)]})


@bp.route('/api/outbounds/<int:out_id>/nodes', methods=['POST'])
def add_pool_node(out_id):
    data = request.get_json(force=True)
    pool_id = db_outbound.add_pool_node(out_id, data['node_id'], data.get('priority'))
    return jsonify({'success': True, 'id': pool_id}), 201


@bp.route('/api/outbounds/<int:out_id>/nodes/<int:pool_id>', methods=['DELETE'])
def remove_pool_node(out_id, pool_id):
    db_outbound.remove_pool_node(pool_id)
    return jsonify({'success': True})


@bp.route('/api/outbounds/<int:out_id>/nodes/reorder', methods=['POST'])
def reorder_pool_nodes(out_id):
    data = request.get_json(force=True)
    db_outbound.sync_pool_nodes(out_id, data['node_ids'])
    return jsonify({'success': True})


@bp.route('/api/services', methods=['GET'])
def list_services():
    return jsonify({'services': [dict(row) for row in db_service.list_all()]})


@bp.route('/api/services', methods=['POST'])
def create_service():
    data = request.get_json(force=True)
    service_id = db_service.create(
        name=data['name'],
        inbound_id=data['inbound_id'],
        outbound_id=data['outbound_id'],
        auto_start=data.get('auto_start', 0),
    )
    return jsonify({'success': True, 'id': service_id}), 201


@bp.route('/api/services/<int:svc_id>', methods=['PUT'])
def update_service(svc_id):
    db_service.update(svc_id, **request.get_json(force=True))
    return jsonify({'success': True})


@bp.route('/api/services/<int:svc_id>', methods=['DELETE'])
def delete_service(svc_id):
    db_service.delete(svc_id)
    return jsonify({'success': True})


@bp.route('/api/services/<int:svc_id>/start', methods=['POST'])
def api_start_service(svc_id):
    result = start_service(svc_id)
    return jsonify(result), 200 if result['success'] else 400


@bp.route('/api/services/<int:svc_id>/stop', methods=['POST'])
def api_stop_service(svc_id):
    result = stop_service(svc_id)
    return jsonify(result), 200 if result['success'] else 400


@bp.route('/api/services/<int:svc_id>/restart', methods=['POST'])
def api_restart_service(svc_id):
    result = restart_service(svc_id)
    return jsonify(result), 200 if result['success'] else 400


@bp.route('/api/services/<int:svc_id>/switch', methods=['POST'])
def api_switch_node(svc_id):
    result = switch_node(svc_id, request.get_json(force=True)['node_id'])
    return jsonify(result), 200 if result['success'] else 400


@bp.route('/api/services/<int:svc_id>/status', methods=['GET'])
def api_service_status(svc_id):
    return jsonify(get_service_status(svc_id))


@bp.route('/api/services/current-nodes', methods=['GET'])
def api_current_nodes():
    result = []
    for service in db_service.list_all():
        outbound_id = service['outbound_id']
        if outbound_id == 0:
            result.append({
                'id': service['id'],
                'outbound_id': 0,
                'current_node': 'direct',
                'status': 'direct',
            })
            continue
        now = get_proxy_now(f'g{outbound_id}')
        result.append({
            'id': service['id'],
            'outbound_id': outbound_id,
            'current_node': now,
            'status': 'running' if (now and now != 'direct') else 'stopped',
        })
    return jsonify({'services': result})
