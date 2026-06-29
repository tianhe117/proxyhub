"""Service lifecycle management.

Coordinates inbound + outbound process pairs.
Uses process/manager.py for actual process control.
"""

import os
import threading
import time
from datetime import datetime

from app.models.service import (
    get_by_id as get_service, get_auto_start_services,
    list_all, update_status,
)
from app.models.outbound import get_by_id as get_outbound, get_pool_nodes
from app.models.node import get_by_id as get_node, update_latency
from app.models.setting import get_setting
from app.process.manager import (
    start_process, stop_service as stop_service_processes,
    stop_all_processes as stop_all_bin_processes,
    get_service_processes
)
from app.services.config_service import (
    generate_service_config, save_service_config, get_outbound_node,
)
from app.checker import generate_temp_config, find_temp_port
from app.checker.script import tcp_ping, url_test
from app.logger import log


# ---------------------------------------------------------------------------
# Failover state (in-memory only, not persisted)
# ---------------------------------------------------------------------------

_failover_state = {}  # {outbound_id: {fail_count, current_node_id, last_check, interval, all_dead_count}}

FAILOVER_CHECK_INTERVAL = 15       # seconds between health check ticks
FAIL_THRESHOLD = 3                 # consecutive failures before switching
ALL_DEAD_INTERVALS = [5*60, 10*60, 15*60, 30*60]  # 递增等待


def _get_normal_interval():
    """Read normal check interval from DB (seconds)."""
    return int(get_setting('check_interval_normal') or 240)


def _get_fail_fast_interval():
    """Read fail-fast check interval from DB (seconds)."""
    return int(get_setting('check_interval_failover') or 30)


def _get_failover_state(outbound_id):
    """Get or initialize failover state for an outbound."""
    if outbound_id not in _failover_state:
        _failover_state[outbound_id] = {
            'fail_count': 0,
            'current_node_id': 0,
            'last_check': 0,
            'interval': _get_fail_fast_interval(),  # 首次检查快速触发
            'all_dead_count': 0,
        }
    return _failover_state[outbound_id]


def _check_node_health(node, tag):
    """Check a single node's health via TCP ping + URL test.

    Returns:
        dict: {healthy: bool, tcp_latency: int, curl_latency: int}
    """
    tcp_timeout = int(get_setting('tcp_timeout') or 3)
    curl_timeout = int(get_setting('curl_timeout') or 5)
    test_url = get_setting('test_url') or 'http://www.gstatic.com/generate_204'

    # TCP ping
    tcp_res = tcp_ping(node['address'], node['port'], tcp_timeout, tag)
    tcp_ok = tcp_res.get('success', False)
    tcp_lat = tcp_res.get('latency_ms', -1)

    curl_lat = -1
    if tcp_ok:
        # URL test — generate temp config, test, cleanup
        config_path = None
        try:
            local_port = find_temp_port()
            config_path = generate_temp_config(node, local_port)
            bin_type = node['bin_type']
            bin_key = f'bin_path_{bin_type if bin_type != "sing-box" else "singbox"}'
            bin_path = get_setting(bin_key) or ''
            if bin_path and not os.path.isabs(bin_path):
                bin_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(
                        os.path.abspath(__file__)))), bin_path
                )

            url_res = url_test(config_path, bin_type, bin_path,
                               local_port, test_url, curl_timeout, tag)
            curl_ok = url_res.get('success', False)
            curl_lat = url_res.get('latency_ms', -1)
        except Exception:
            curl_ok = False
        finally:
            if config_path and os.path.exists(config_path):
                try:
                    os.remove(config_path)
                except Exception:
                    pass
    else:
        curl_ok = False

    return {
        'healthy': tcp_ok and curl_ok,
        'tcp_latency': tcp_lat,
        'curl_latency': curl_lat,
    }


def _do_failover(outbound_id, pool, current_node_id):
    """Scan pool for a healthy node and switch all services on this outbound.

    Returns:
        bool: True if switched to a new node, False if all nodes dead
    """
    outbound = get_outbound(outbound_id)
    ob_name = outbound['name'] if outbound else f'#{outbound_id}'
    tag = f'failover_{outbound_id}_{int(time.time())}'

    log('warn', 'failover',
        f'outbound#{outbound_id} ({ob_name}): '
        f'scanning {len(pool)} nodes in pool (skipping current node_id={current_node_id})...')

    # Scan all nodes except current
    best_node_id = None
    best_tcp = -1
    for entry in pool:
        nid = entry['node_id']
        if nid == current_node_id:
            continue

        node = get_node(nid)
        if not node:
            continue

        health = _check_node_health(node, tag)

        # Update DB latency
        update_latency(nid, health['tcp_latency'], health['curl_latency'],
                       datetime.now().isoformat())

        if health['healthy']:
            log('info', 'failover',
                f'  candidate {node["name"]}: OK '
                f'(tcp={health["tcp_latency"]}ms, curl={health["curl_latency"]}ms)')
            if best_node_id is None or health['tcp_latency'] < best_tcp:
                best_node_id = nid
                best_tcp = health['tcp_latency']
        else:
            log('info', 'failover',
                f'  candidate {node["name"]}: FAIL '
                f'(tcp={health["tcp_latency"]}ms, curl={health["curl_latency"]}ms)')

    if best_node_id is not None:
        # Found a healthy node — update state
        new_node = get_node(best_node_id)
        state = _get_failover_state(outbound_id)
        state['current_node_id'] = best_node_id
        state['fail_count'] = 0
        state['all_dead_count'] = 0
        state['interval'] = _get_normal_interval()

        # Restart ALL running services that share this outbound
        restarted = []
        for svc in list_all():
            if svc['outbound_id'] != outbound_id:
                continue
            if svc['status'] != 'running':
                continue
            result = _start_service_with_node(svc['id'], best_node_id)
            if result['success']:
                restarted.append(svc['name'])
            else:
                log('error', 'failover',
                    f'{svc["name"]}: restart failed — {result["message"]}')

        if restarted:
            log('ok', 'failover',
                f'outbound#{outbound_id} ({ob_name}): '
                f'switched to {new_node["name"]} (tcp={best_tcp}ms), '
                f'restarted: {", ".join(restarted)}')
        else:
            log('info', 'failover',
                f'outbound#{outbound_id} ({ob_name}): '
                f'switched to {new_node["name"]} (tcp={best_tcp}ms), '
                f'but no running services to restart')
        return True
    else:
        # All nodes dead — increment wait
        state = _get_failover_state(outbound_id)
        state['fail_count'] = 0
        state['all_dead_count'] += 1
        idx = min(state['all_dead_count'] - 1, len(ALL_DEAD_INTERVALS) - 1)
        state['interval'] = ALL_DEAD_INTERVALS[idx]
        state['last_check'] = time.time()
        log('warn', 'failover',
            f'outbound#{outbound_id} ({ob_name}): '
            f'all {len(pool)} nodes unavailable, '
            f'{state["interval"] // 60}min until next check')
        return False


def _start_service_with_node(service_id, node_id):
    """Start a service using a specific node (failover override).

    Like start_service() but forces a specific node via node_id parameter
    to get_outbound_node().
    """
    svc = get_service(service_id)
    if not svc:
        return {'success': False, 'message': 'Service not found'}

    service_name = svc['name']

    # Kill leftover processes
    procs = get_service_processes(service_name)
    if procs:
        stop_service_processes(service_name)

    # Generate config with node override
    from app.models.inbound import get_by_id as get_inbound
    inbound = get_inbound(svc['inbound_id'])
    outbound = get_outbound(svc['outbound_id'])
    if not inbound or not outbound:
        return {'success': False, 'message': 'Inbound or outbound not found'}

    node = get_outbound_node(outbound, node_id=node_id)
    if not node:
        return {'success': False, 'message': 'Node not found'}

    from app.engine import build_outbound_config
    from app.engine.xray import build_xray_inbound
    from app.services.config_service import (
        check_inbound_port, find_available_port, save_service_config,
    )

    ok, err = check_inbound_port(inbound['port'])
    if not ok:
        return {'success': False, 'message': err}

    socks_port = find_available_port()
    xray_in = build_xray_inbound(inbound, socks_port)
    outbound_config, _ = build_outbound_config(node, socks_port)
    bin_type = node['bin_type']

    xray_in_path, out_path = save_service_config(
        service_name, xray_in, bin_type, outbound_config
    )

    try:
        out_pid = start_process(service_name, bin_type, out_path, role='out')
        in_pid = start_process(service_name, 'xray', xray_in_path, role='in')
        update_status(service_id, 'running')
        log('ok', 'service', f'Service {service_name} started '
            f'(in:{in_pid} out:{out_pid} → {node["name"]})')
        return {'success': True, 'message': f'Service {service_name} started'}
    except Exception as e:
        stop_service_processes(service_name)
        update_status(service_id, 'error')
        log('error', 'service', f'Failed to start {service_name}: {e}')
        return {'success': False, 'message': str(e)}


def start_service(service_id):
    """Start a service: validate → generate config → launch processes.

    For auto-type outbounds with an existing failover state, uses the
    current_node_id from failover state instead of pool[0].

    Returns:
        dict: {success, message}
    """
    svc = get_service(service_id)
    if not svc:
        return {'success': False, 'message': 'Service not found'}

    service_name = svc['name']

    # For auto-type outbounds with failover state, delegate to _start_service_with_node
    # (it handles process cleanup internally)
    outbound = get_outbound(svc['outbound_id'])
    if outbound and outbound['type'] == 'auto':
        state = _get_failover_state(outbound['id'])
        if state['current_node_id'] != 0:
            return _start_service_with_node(service_id, state['current_node_id'])

    # Check for leftover processes and kill them
    procs = get_service_processes(service_name)
    if procs:
        log('warn', 'service', f'Found {len(procs)} leftover process(es) for {service_name}, killing them first')
        stop_service_processes(service_name)

    # Generate configuration (default path — uses pool[0] for auto)
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
_health_app = None  # saved for restart


def stop_health_check_daemon():
    """Stop the health-check daemon thread."""
    global _health_thread, _health_shutdown
    if _health_thread is None:
        return
    _health_shutdown = True
    _health_thread.join(timeout=5)
    _health_thread = None
    _health_shutdown = False
    log('info', 'system', 'Health check daemon stopped')


def restart_health_check_daemon():
    """Restart the health-check daemon (stop + start with saved app)."""
    stop_health_check_daemon()
    if _health_app is not None:
        start_health_check_daemon(_health_app)
    else:
        log('error', 'system', 'Cannot restart health check daemon: no app reference saved')


def start_health_check_daemon(app):
    """Launch background thread that monitors services and auto-restarts.

    If a service has DB status='running' but its in/out processes
    are missing, kill leftovers and restart it.
    """
    global _health_thread, _health_app
    if _health_thread is not None:
        return  # already running

    _health_app = app

    def _loop():
        while not _health_shutdown:
            time.sleep(FAILOVER_CHECK_INTERVAL)
            try:
                with app.app_context():
                    # Phase 1: Process alive check (all running services)
                    for svc in list_all():
                        if svc['status'] != 'running':
                            continue

                        service_name = svc['name']
                        procs = get_service_processes(service_name)
                        has_in = any('_in' in k for k in procs)
                        has_out = any('_out' in k for k in procs)

                        if procs and has_in and has_out:
                            continue

                        # Something is wrong — kill leftovers, restart
                        if procs:
                            missing = []
                            if not has_in:
                                missing.append('in')
                            if not has_out:
                                missing.append('out')
                            log('warn', 'health', f'{service_name}: missing {missing}, {len(procs)} leftover process(es) — restarting')
                            stop_service_processes(service_name)
                            time.sleep(0.3)

                        try:
                            result = start_service(svc['id'])
                            if result['success']:
                                log('ok', 'health', f'{service_name}: auto-restarted')
                            else:
                                log('error', 'health', f'{service_name}: restart failed — {result["message"]}')
                        except Exception as e:
                            log('error', 'health', f'{service_name}: restart error — {e}')

                    # Phase 2: Node health check (auto-type outbounds, deduplicated)
                    now = time.time()
                    checked_outbound_ids = set()
                    for svc in list_all():
                        if svc['status'] != 'running':
                            continue

                        outbound_id = svc['outbound_id']
                        if outbound_id in checked_outbound_ids:
                            continue  # already checked this outbound in this tick

                        outbound = get_outbound(outbound_id)
                        if not outbound or outbound['type'] != 'auto':
                            continue

                        # At least one service on this outbound must be running
                        service_name = svc['name']
                        procs = get_service_processes(service_name)
                        has_in = any('_in' in k for k in procs)
                        has_out = any('_out' in k for k in procs)
                        if not (procs and has_in and has_out):
                            continue

                        checked_outbound_ids.add(outbound_id)
                        state = _get_failover_state(outbound_id)

                        # Check interval
                        if now - state['last_check'] < state['interval']:
                            continue

                        state['last_check'] = now

                        # Verify current_node_id is still in pool
                        pool = get_pool_nodes(outbound_id)
                        if not pool:
                            log('info', 'failover',
                                f'outbound#{outbound_id} ({outbound["name"]}): pool is empty, skip')
                            continue

                        pool_ids = {e['node_id'] for e in pool}
                        if state['current_node_id'] != 0 and state['current_node_id'] not in pool_ids:
                            log('info', 'failover',
                                f'outbound#{outbound_id} ({outbound["name"]}): '
                                f'current_node_id {state["current_node_id"]} not in pool, resetting to pool[0]')
                            state['current_node_id'] = pool[0]['node_id']
                            state['fail_count'] = 0

                        # Initialize on first check
                        if state['current_node_id'] == 0:
                            state['current_node_id'] = pool[0]['node_id']
                            state['fail_count'] = 0
                            log('info', 'failover',
                                f'outbound#{outbound_id} ({outbound["name"]}): '
                                f'first check, init to pool[0] node_id={state["current_node_id"]}')

                        # Check current node health
                        current_node = get_node(state['current_node_id'])
                        if not current_node:
                            state['current_node_id'] = pool[0]['node_id']
                            state['fail_count'] = 0
                            current_node = get_node(state['current_node_id'])

                        tag = f'failover_{outbound_id}_{int(now)}'
                        health = _check_node_health(current_node, tag)

                        # Update DB latency for current node
                        update_latency(
                            state['current_node_id'],
                            health['tcp_latency'], health['curl_latency'],
                            datetime.now().isoformat()
                        )

                        if health['healthy']:
                            state['fail_count'] = 0
                            state['all_dead_count'] = 0
                            state['interval'] = _get_normal_interval()
                        else:
                            state['fail_count'] += 1
                            log('warn', 'failover',
                                f'outbound#{outbound_id} ({outbound["name"]}): '
                                f'node {current_node["name"]} FAILED '
                                f'({state["fail_count"]}/{FAIL_THRESHOLD}) '
                                f'tcp={health["tcp_latency"]}ms, curl={health["curl_latency"]}ms')

                            if state['fail_count'] >= FAIL_THRESHOLD:
                                _do_failover(outbound_id, pool, state['current_node_id'])
                            else:
                                state['interval'] = _get_fail_fast_interval()

            except Exception as e:
                log('error', 'health', f'Health check loop error: {e}')

    _health_thread = threading.Thread(target=_loop, daemon=True)
    _health_thread.start()
    log('info', 'system', f'Health check daemon started (interval={FAILOVER_CHECK_INTERVAL}s)')


# ---------------------------------------------------------------------------
# Auto-start daemon
# ---------------------------------------------------------------------------

def start_auto_start_daemon(app):
    """Launch a background thread that starts auto_start=1 services."""
    def _daemon():
        # Wait for Flask to be fully up
        time.sleep(2)
        with app.app_context():
            # Kill any leftover processes from previous runs (e.g. after Python was killed)
            killed = stop_all_bin_processes()
            if killed:
                log('info', 'system', f'Cleaned up {killed} orphaned process(es) from previous run')
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
# Failover query API
# ---------------------------------------------------------------------------

def get_current_node(service_id):
    """Return the current node for a service's outbound.

    For auto-type: returns the failover-selected node (or pool[0] if none).
    For single-type: returns the configured node.
    For direct: returns None.

    Returns:
        dict: {node_id, node_name, outbound_type} or None
    """
    svc = get_service(service_id)
    if not svc:
        return None

    outbound = get_outbound(svc['outbound_id'])
    if not outbound:
        return None

    if outbound['type'] == 'direct':
        return None

    if outbound['type'] == 'single':
        node = get_outbound_node(outbound)
        if node:
            return {
                'node_id': node['id'],
                'node_name': node['name'],
                'outbound_type': 'single',
            }
        return None

    # auto type
    state = _get_failover_state(outbound['id'])
    if state['current_node_id'] != 0:
        node = get_node(state['current_node_id'])
        if node:
            return {
                'node_id': node['id'],
                'node_name': node['name'],
                'outbound_type': 'auto',
            }

    # Fallback to pool[0]
    pool = get_pool_nodes(outbound['id'])
    if pool:
        node = get_node(pool[0]['node_id'])
        if node:
            return {
                'node_id': node['id'],
                'node_name': node['name'],
                'outbound_type': 'auto',
            }

    return None
