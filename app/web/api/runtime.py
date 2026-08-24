"""Runtime, upgrade, and log API routes."""

import glob
import os

from flask import jsonify, request, send_file

from app import config
from app.services.runtime import (
    get_status,
    restart_singbox,
    start_singbox,
    stop_singbox,
)
from app.singbox import upgrade
from app.web.api import bp


@bp.route('/api/status', methods=['GET'])
def api_status():
    return jsonify(get_status())


@bp.route('/api/start', methods=['POST'])
def api_start():
    result = start_singbox()
    return jsonify(result), 200 if result['success'] else 500


@bp.route('/api/stop', methods=['POST'])
def api_stop():
    result = stop_singbox()
    return jsonify(result), 200 if result['success'] else 500


@bp.route('/api/restart', methods=['POST'])
def api_restart():
    result = restart_singbox()
    return jsonify(result), 200 if result['success'] else 500


@bp.route('/api/upgrade/status', methods=['GET'])
def upgrade_status():
    result = upgrade.check_upgrade()
    return (jsonify(result), 502) if not result['success'] else jsonify(result)


@bp.route('/api/upgrade/download', methods=['POST'])
def upgrade_download():
    result = upgrade.download_upgrade()
    return (jsonify(result), 502) if not result['success'] else jsonify(result)


def _current_log_file():
    files = glob.glob(os.path.join(config.LOGS_DIR, '*.log'))
    return max(files, key=os.path.getmtime) if files else None


@bp.route('/api/logs', methods=['GET'])
def api_logs():
    try:
        tail = min(int(request.args.get('tail', 200)), 1000)
    except ValueError:
        tail = 200
    path = _current_log_file()
    if not path:
        return jsonify({'file': None, 'lines': []})
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as file:
            lines = file.read().splitlines()[-tail:]
    except OSError as error:
        return jsonify({'file': None, 'lines': [], 'error': str(error)})
    return jsonify({'file': os.path.basename(path), 'lines': lines})


@bp.route('/api/logs/download', methods=['GET'])
def api_logs_download():
    path = _current_log_file()
    if not path:
        return jsonify({'success': False, 'message': 'No log file'}), 404
    return send_file(path, as_attachment=True)
