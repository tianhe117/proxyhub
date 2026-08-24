"""Subscription CRUD and refresh API routes."""

from flask import jsonify, request

from app.db import subscription as db_sub
from app.services.subscriptions import refresh_subscription as refresh_subscription_service
from app.web.api import bp


@bp.route('/api/subscriptions', methods=['GET'])
def list_subscriptions():
    rows = [dict(row) for row in db_sub.list_all() if row['id'] > 0]
    return jsonify({'subscriptions': rows})


@bp.route('/api/subscriptions', methods=['POST'])
def create_subscription():
    data = request.get_json(force=True)
    sub_id = db_sub.create(
        data['name'],
        data['url'],
        data.get('filter_keywords', ''),
        data.get('exclude_keywords', ''),
    )
    return jsonify({'success': True, 'id': sub_id}), 201


@bp.route('/api/subscriptions/<int:sub_id>', methods=['PUT'])
def update_subscription(sub_id):
    db_sub.update(sub_id, **request.get_json(force=True))
    return jsonify({'success': True})


@bp.route('/api/subscriptions/<int:sub_id>', methods=['DELETE'])
def delete_subscription(sub_id):
    if sub_id == 0:
        return jsonify({'success': False, 'message': 'Cannot delete sentinel'}), 400
    db_sub.delete(sub_id)
    return jsonify({'success': True})


@bp.route('/api/subscriptions/<int:sub_id>/refresh', methods=['POST'])
def refresh_subscription(sub_id):
    return jsonify(refresh_subscription_service(sub_id))
