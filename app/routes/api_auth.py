"""Authentication API routes."""

from flask import Blueprint, request, jsonify

from app.services.auth_service import login, logout
from . import auth_required

api_auth = Blueprint('api_auth', __name__, url_prefix='/api/auth')


@api_auth.route('/login', methods=['POST'])
def auth_login():
    ok, error = login(
        request.form.get('username', '') or request.json.get('username', ''),
        request.form.get('password', '') or request.json.get('password', '')
    )
    if ok:
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': error}), 401


@api_auth.route('/logout', methods=['POST'])
def auth_logout():
    logout()
    return jsonify({'success': True})
