"""Inbound API routes (§4.7)."""

from flask import Blueprint, request, jsonify

from app.models.inbound import list_all, get_by_id, create, update, delete
from . import auth_required

api_inbounds = Blueprint('api_inbounds', __name__, url_prefix='/api/inbounds')


@api_inbounds.route('/', methods=['GET'])
@auth_required
def list_inbounds():
    return jsonify([dict(r) for r in list_all()])


@api_inbounds.route('/', methods=['POST'])
@auth_required
def create_inbound():
    data = request.get_json(force=True) or {}
    in_id = create(
        data.get('name', ''), data.get('protocol', ''),
        data.get('listen_addr', '0.0.0.0'), data.get('port', 0),
        data.get('params_json', '{}')
    )
    return jsonify({'success': True, 'id': in_id})


@api_inbounds.route('/<int:in_id>', methods=['PUT'])
@auth_required
def update_inbound(in_id):
    data = request.get_json(force=True) or {}
    update(in_id, **data)
    return jsonify({'success': True})


@api_inbounds.route('/<int:in_id>', methods=['DELETE'])
@auth_required
def delete_inbound(in_id):
    delete(in_id)
    return jsonify({'success': True})
