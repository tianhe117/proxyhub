"""Service API routes (§4.9)."""

from flask import Blueprint, request, jsonify

from app.models.service import (
    list_all, get_by_id, create, update, delete,
)
from app.services.service_manager import (
    start_service, stop_service, restart_service,
)
from . import auth_required

api_services = Blueprint('api_services', __name__, url_prefix='/api/services')


@api_services.route('/', methods=['GET'])
@auth_required
def list_services():
    return jsonify([dict(s) for s in list_all()])


@api_services.route('/<int:svc_id>', methods=['GET'])
@auth_required
def get_service(svc_id):
    svc = get_by_id(svc_id)
    if not svc:
        return jsonify({'success': False, 'message': 'Not found'}), 404
    return jsonify(dict(svc))


@api_services.route('/', methods=['POST'])
@auth_required
def create_service():
    data = request.get_json(force=True) or {}
    svc_id = create(
        data.get('name', ''), data.get('inbound_id', 0),
        data.get('outbound_id', 0), data.get('auto_start', 0)
    )
    return jsonify({'success': True, 'id': svc_id})


@api_services.route('/<int:svc_id>', methods=['PUT'])
@auth_required
def update_service(svc_id):
    data = request.get_json(force=True) or {}
    update(svc_id, **{k: v for k, v in data.items()
           if k in ('name', 'inbound_id', 'outbound_id', 'auto_start')})
    return jsonify({'success': True})


@api_services.route('/<int:svc_id>', methods=['DELETE'])
@auth_required
def delete_service(svc_id):
    delete(svc_id)
    return jsonify({'success': True})


@api_services.route('/<int:svc_id>/start', methods=['POST'])
@auth_required
def start_service_handler(svc_id):
    result = start_service(svc_id)
    return jsonify(result), 200 if result['success'] else 400


@api_services.route('/<int:svc_id>/stop', methods=['POST'])
@auth_required
def stop_service_handler(svc_id):
    result = stop_service(svc_id)
    return jsonify(result)


@api_services.route('/<int:svc_id>/restart', methods=['POST'])
@auth_required
def restart_service_handler(svc_id):
    result = restart_service(svc_id)
    return jsonify(result), 200 if result['success'] else 400
