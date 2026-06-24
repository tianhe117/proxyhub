"""Subscription API routes (§4.5)."""

from flask import Blueprint, request, jsonify

from app.models.subscription import (
    list_all, get_by_id, create, update, delete,
)
from app.services.subscription_service import refresh_subscription
from . import auth_required

api_subscriptions = Blueprint('api_subscriptions', __name__, url_prefix='/api/subscriptions')


@api_subscriptions.route('/', methods=['GET'])
@auth_required
def list_subscriptions():
    subs = list_all()
    # Count nodes per subscription for the list view
    from app.models.node import list_by_sub
    result = []
    for s in subs:
        d = dict(s)
        d['node_count'] = len(list_by_sub(s['id']))
        result.append(d)
    return jsonify(result)


@api_subscriptions.route('/', methods=['POST'])
@auth_required
def create_subscription():
    data = request.get_json(force=True) or {}
    sub_id = create(
        data.get('name', ''), data.get('url', ''),
        data.get('filter_keywords', ''), data.get('exclude_keywords', '')
    )
    return jsonify({'success': True, 'id': sub_id})


@api_subscriptions.route('/<int:sub_id>', methods=['PUT'])
@auth_required
def update_subscription(sub_id):
    data = request.get_json(force=True) or {}
    update(sub_id, **{k: v for k, v in data.items()
           if k in ('name', 'url', 'filter_keywords', 'exclude_keywords')})
    return jsonify({'success': True})


@api_subscriptions.route('/<int:sub_id>', methods=['DELETE'])
@auth_required
def delete_subscription(sub_id):
    delete(sub_id)
    return jsonify({'success': True})


@api_subscriptions.route('/<int:sub_id>/refresh', methods=['POST'])
@auth_required
def refresh_subscription_handler(sub_id):
    result = refresh_subscription(sub_id)
    return jsonify(result), 200 if result['success'] else 400
