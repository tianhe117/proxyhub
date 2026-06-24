"""Upgrade API routes (§4.4)."""

from flask import Blueprint, jsonify

from app.services.upgrade_service import check_upgrade, download_upgrade
from . import auth_required

api_upgrade = Blueprint('api_upgrade', __name__, url_prefix='/api/upgrade')


@api_upgrade.route('/check/<bin_name>', methods=['GET'])
@auth_required
def check_upgrade_handler(bin_name):
    return jsonify(check_upgrade(bin_name))


@api_upgrade.route('/download/<bin_name>', methods=['POST'])
@auth_required
def download_upgrade_handler(bin_name):
    result = download_upgrade(bin_name)
    return jsonify(result), 200 if result['success'] else 400
