"""Service lifecycle management (§5.3, §5.4).

Coordinates inbound + outbound process pairs.
"""

import os
import threading
import time

from app.models.service import get_by_id as get_service, update_status, get_auto_start_services
from app.process.manager import (
    start_process, stop_all_for_service, get_process_status
)
from app.services.config_service import (
    generate_service_config, save_service_config
)
from app.logger import log


def start_service(service_id):
    """Start a service: validate → generate config → launch processes (§5.3).

    Returns:
        dict: {success, message}
    """
    svc = get_service(service_id)
    if not svc:
        return {'success': False, 'message': 'Service not found'}

    service_name = svc['name']

    # Check if already running (scan PID files for this service)
    from app.process.manager import get_pid_dir as _get_pid_dir
    pid_dir = _get_pid_dir()
    prefix = f'{service_name}_'
    if os.path.isdir(pid_dir):
        for fname in os.listdir(pid_dir):
            if fname.startswith(prefix) and fname.endswith('.pid'):
                key = fname[len(prefix):-4]
                if get_process_status(service_name, key) == 'running':
                    return {'success': False, 'message': f'Service {service_name} is already running'}

    # Generate configuration
    gen = generate_service_config(service_id)
    if not gen['success']:
        return gen

    # Write config files
    xray_in_path, out_path = save_service_config(
        gen['service_name'], gen['xray_in'],
        gen['outbound_bin'], gen['outbound_config']
    )

    try:
        # 1. Start outbound binary first (so SOCKS5 endpoint is ready)
        out_pid = start_process(service_name, gen['outbound_bin'], out_path, role='out')

        # 2. Start Xray inbound
        in_pid = start_process(service_name, 'xray', xray_in_path, role='in')

        update_status(service_id, 'running')
        log('ok', 'service', f'Service {service_name} started '
            f'(in:{in_pid} out:{out_pid} → {gen["node_name"]})')

        return {
            'success': True,
            'message': f'Service {service_name} started',
        }
    except Exception as e:
        # Rollback — stop both processes
        stop_all_for_service(service_name)
        update_status(service_id, 'error')
        log('error', 'service', f'Failed to start {service_name}: {e}')
        return {'success': False, 'message': str(e)}


def stop_service(service_id):
    """Stop a service — kill both inbound and outbound processes (§5.4)."""
    svc = get_service(service_id)
    if not svc:
        return {'success': False, 'message': 'Service not found'}

    service_name = svc['name']
    stop_all_for_service(service_name)
    update_status(service_id, 'stopped')
    log('info', 'service', f'Service {service_name} stopped')
    return {'success': True, 'message': f'Service {service_name} stopped'}


def restart_service(service_id):
    """Restart a service."""
    stop = stop_service(service_id)
    if not stop['success']:
        return stop
    # Brief pause to let ports free up
    time.sleep(0.5)
    return start_service(service_id)


# ---------------------------------------------------------------------------
# Auto-start daemon (§13)
# ---------------------------------------------------------------------------

def start_auto_start_daemon(app):
    """Launch a background thread that starts auto_start=1 services."""
    def _daemon():
        # Wait for Flask to be fully up
        time.sleep(2)
        with app.app_context():
            services = get_auto_start_services()
            for svc in services:
                try:
                    log('info', 'system', f'Auto-starting: {svc["name"]}')
                    start_service(svc['id'])
                except Exception as e:
                    log('error', 'system', f'Auto-start failed for {svc["name"]}: {e}')

    t = threading.Thread(target=_daemon, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Reserved — automatic failover (§9.1)
# ---------------------------------------------------------------------------

def _check_and_failover(service_id):
    """Reserved for automatic node failover (not yet implemented)."""
    pass
