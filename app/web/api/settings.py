"""Persistent user settings API routes."""

from flask import jsonify, request

from app import settings as app_settings
from app.web.api import bp


@bp.route('/api/settings', methods=['GET'])
def get_settings():
    values = app_settings.get_all_settings()
    if values.get('web_password'):
        values['web_password'] = '******'
    return jsonify({'settings': values})


@bp.route('/api/settings', methods=['POST'])
def update_settings():
    values = request.get_json(force=True)
    if values.get('web_password') == '******':
        values.pop('web_password')
    app_settings.update_settings(values)
    return jsonify({'success': True})
