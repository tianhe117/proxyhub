"""Settings API routes (§4.2)."""

from flask import Blueprint, request, jsonify

from app.models.setting import get_all_settings, update_settings, reset_to_defaults
from . import auth_required

api_settings = Blueprint('api_settings', __name__, url_prefix='/api/settings')


@api_settings.route('/', methods=['GET'])
@auth_required
def get_settings():
    settings = get_all_settings()
    # Mask password
    if 'web_password' in settings and settings['web_password']:
        settings['web_password'] = '******'
    return jsonify(settings)


@api_settings.route('/', methods=['POST'])
@auth_required
def update_settings_handler():
    data = request.get_json(force=True) or {}
    # Don't update password if masked value sent
    if data.get('web_password') == '******':
        data.pop('web_password', None)
    update_settings(data)
    return jsonify({'success': True})


@api_settings.route('/reset', methods=['POST'])
@auth_required
def reset_settings():
    reset_to_defaults()
    return jsonify({'success': True})
