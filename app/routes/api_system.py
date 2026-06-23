"""System info API routes (§4.11)."""

import os
import platform

from flask import Blueprint, jsonify

from app.settings import get_db_path, get_data_dir
from app.settings import BIN_REGISTRY
from app.process.manager import get_version, stop_all_processes
from app.services.service_manager import start_service
from app.models.service import get_auto_start_services, update_status
from app.logger import log
from . import auth_required

api_system = Blueprint('api_system', __name__, url_prefix='/api/system')


@api_system.route('/info', methods=['GET'])
@auth_required
def system_info():
    db_size = '0 B'
    db_path = get_db_path()
    if os.path.exists(db_path):
        size = os.path.getsize(db_path)
        from app.utils.helpers import format_size
        db_size = format_size(size)

    bins = {}
    for name in BIN_REGISTRY:
        display_name = name if name != 'sing-box' else 'sing-box'
        bins[name] = get_version(display_name)

    return jsonify({
        'platform': platform.platform(),
        'python': platform.python_version(),
        'db_size': db_size,
        'bins': bins,
    })


@api_system.route('/restart-all', methods=['POST'])
@auth_required
def restart_all():
    """Stop all processes, then restart auto-start services."""
    # 1. Stop all processes
    killed = stop_all_processes()
    # 2. Reset all service statuses to stopped
    from app.models.service import list_all
    for svc in list_all():
        if svc['status'] != 'stopped':
            update_status(svc['id'], 'stopped')
    log('info', 'system', f'Stopped {killed} process(es)')
    # 3. Restart auto-start services
    auto_svcs = get_auto_start_services()
    started = 0
    for svc in auto_svcs:
        try:
            result = start_service(svc['id'])
            if result['success']:
                started += 1
        except Exception as e:
            log('error', 'system', f'Failed to start {svc["name"]}: {e}')
    log('info', 'system', f'Restarted {started}/{len(auto_svcs)} auto-start service(s)')
    return jsonify({'success': True, 'killed': killed, 'started': started})
