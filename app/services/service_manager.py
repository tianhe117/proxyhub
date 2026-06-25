"""Service lifecycle management.

Coordinates inbound + outbound process pairs.
Uses process/manager.py for actual process control.
"""

import threading
import time

from app.models.service import (
    get_by_id as get_service, get_auto_start_services,
    list_all, update_status,
)
from app.process.manager import (
    start_process, stop_service as stop_service_processes,
    is_service_running, get_service_processes
)
from app.services.config_service import (
    generate_service_config, save_service_config
)
from app.logger import log


def start_service(service_id):
    """Start a service: validate → generate config → launch processes.

    Returns:
        dict: {success, message}
    """
    svc = get_service(service_id)
    if not svc:
        return {'success': False, 'message': 'Service not found'}

    service_name = svc['name']

    # Check for leftover processes and kill them
    procs = get_service_processes(service_name)
    if procs:
        log('warn', 'service', f'Found {len(procs)} leftover process(es) for {service_name}, killing them first')
        stop_service_processes(service_name)

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
        stop_service_processes(service_name)
        update_status(service_id, 'error')
        log('error', 'service', f'Failed to start {service_name}: {e}')
        return {'success': False, 'message': str(e)}


def stop_service(service_id):
    """Stop a service — kill both inbound and outbound processes."""
    svc = get_service(service_id)
    if not svc:
        return {'success': False, 'message': 'Service not found'}

    service_name = svc['name']
    result = stop_service_processes(service_name)

    if result['success']:
        update_status(service_id, 'stopped')
        log('info', 'service', f'Service {service_name} stopped')
    else:
        log('error', 'service', f'Service {service_name} stop failed: {result["message"]}')

    return {
        'success': result['success'],
        'message': f'Service {service_name}: {result["message"]}',
    }


def restart_service(service_id):
    """Restart a service: stop → wait → start."""
    stop = stop_service(service_id)
    if not stop['success']:
        return stop

    # Brief pause to let ports free up
    time.sleep(0.5)

    return start_service(service_id)


# ---------------------------------------------------------------------------
# Health-check daemon — monitors services and auto-restarts on failure
# ---------------------------------------------------------------------------

_health_thread = None
_health_shutdown = False

HEALTH_CHECK_INTERVAL = 15  # seconds


def start_health_check_daemon(app):
    """Launch background thread that monitors services and auto-restarts.

    If a service has DB status='running' but its in/out processes
    are missing, kill leftovers and restart it.
    """
    global _health_thread
    if _health_thread is not None:
        return  # already running

    def _loop():
        while not _health_shutdown:
            time.sleep(HEALTH_CHECK_INTERVAL)
            try:
                with app.app_context():
                    for svc in list_all():
                        if svc['status'] != 'running':
                            continue  # only care about intended-running services

                        service_name = svc['name']
                        procs = get_service_processes(service_name)
                        has_in = any('_in' in k for k in procs)
                        has_out = any('_out' in k for k in procs)

                        if procs and has_in and has_out:
                            # Everything is fine
                            continue

                        # Something is wrong — kill leftovers, restart
                        if procs:
                            missing = []
                            if not has_in:
                                missing.append('in')
                            if not has_out:
                                missing.append('out')
                            log('warn', 'health', f'{service_name}: missing {missing}, {len(procs)} leftover process(es) — restarting')

                            # Kill leftovers first
                            stop_service_processes(service_name)
                            time.sleep(0.3)

                        # Restart
                        try:
                            result = start_service(svc['id'])
                            if result['success']:
                                log('ok', 'health', f'{service_name}: auto-restarted')
                            else:
                                log('error', 'health', f'{service_name}: restart failed — {result["message"]}')
                        except Exception as e:
                            log('error', 'health', f'{service_name}: restart error — {e}')
            except Exception as e:
                log('error', 'health', f'Health check loop error: {e}')

    _health_thread = threading.Thread(target=_loop, daemon=True)
    _health_thread.start()
    log('info', 'system', f'Health check daemon started (interval={HEALTH_CHECK_INTERVAL}s)')


# ---------------------------------------------------------------------------
# Auto-start daemon
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
