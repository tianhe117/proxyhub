"""sing-box configuration and resident-process orchestration."""

from app.db import inbound as db_inbound
from app.db import node as db_node
from app.db import outbound as db_outbound
from app.db import service as db_service
from app.singbox import (
    build_config,
    get_version as sb_get_version,
    is_running as sb_is_running,
    restart as sb_restart,
    start as sb_start,
    stop as sb_stop,
    write_config,
)
from app.utils import log


def apply_config():
    """Assemble DB state and atomically write sing-box config.json."""
    db_state = {
        'nodes': [dict(r) for r in db_node.list_all()],
        'inbounds': [dict(r) for r in db_inbound.list_all()],
        'outbounds': [dict(r) for r in db_outbound.list_all()],
        'outbound_nodes': [dict(r) for r in db_outbound.list_all_pool_entries()],
        'services': [dict(r) for r in db_service.list_all()],
    }
    config = build_config(db_state)
    path = write_config(config)
    log.info(f'config.json generated at {path}')
    return path


def start_singbox():
    """Apply config and start sing-box, restarting it if already running."""
    try:
        apply_config()
    except Exception as e:
        log.error(f'config apply failed: {e}')
        return {
            'success': False,
            'message': f'Config apply failed: {e}',
            'running': sb_is_running(),
        }

    if sb_is_running():
        result = sb_restart()
        return {
            'success': result['success'],
            'message': result['message'],
            'running': result['success'],
        }
    try:
        pid = sb_start()
        return {
            'success': True,
            'message': f'sing-box started (PID {pid})',
            'pid': pid,
            'running': True,
        }
    except Exception as e:
        log.error(f'sing-box start failed: {e}')
        return {'success': False, 'message': str(e), 'running': False}


def stop_singbox():
    """Stop the resident sing-box process."""
    result = sb_stop()
    return {
        'success': result['success'],
        'message': result['message'],
        'running': False,
    }


def restart_singbox():
    """Re-apply config and restart sing-box."""
    try:
        apply_config()
    except Exception as e:
        log.error(f'config apply failed: {e}')
        return {
            'success': False,
            'message': f'Config apply failed: {e}',
            'running': sb_is_running(),
        }
    result = sb_restart()
    return {
        'success': result['success'],
        'message': result['message'],
        'running': result['success'],
    }


def get_status():
    """Return sing-box running state and version."""
    running = sb_is_running()
    # The installed binary can report its version without a running process.
    version = sb_get_version()
    return {'running': running, 'version': version}
