"""Route registration, Flask application factory, and authentication decorator (§13, §5.1).

Each API route handler must be ≤ 10 lines (§8.1).
"""

import os
import re
import signal
import threading

from flask import Flask, redirect, url_for, session, jsonify, request

from app.services.auth_service import is_authenticated


def _shutdown():
    """Graceful shutdown: stop daemon, flush WAL to DB file."""
    try:
        from app.services.service_manager import stop_health_check_daemon
        stop_health_check_daemon()
    except Exception:
        pass
    try:
        from app.models.database import get_db, close_db
        get_db()
        close_db()
    except Exception:
        pass
    print('[shutdown] done')


def _on_sigterm(_signum, _frame):
    t = threading.Thread(target=_shutdown, daemon=True)
    t.start()
    t.join(timeout=5)
    os._exit(0)


def create_app():
    """Create and configure the Flask application."""
    import os as _os
    from datetime import timedelta
    _base = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    app = Flask(__name__, template_folder=_os.path.join(_base, 'templates'))

    # Trust nginx proxy headers (X-Forwarded-Proto/Host/For)
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1, x_proto=1)

    # Session persists for 30 days
    app.permanent_session_lifetime = timedelta(days=30)

    # Suppress werkzeug request logs (avoids polling log loops)
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    register_blueprints(app)

    # Install the web logger (intercept stdout/stderr)
    from app.logger import web_logger
    web_logger.install()

    # Initialize database
    from app.models.database import init_db, close_db
    with app.app_context():
        init_db()

        # Fixed secret key (persists across restarts)
        from app.models.setting import get_setting, set_setting
        secret = get_setting('secret_key')
        if not secret:
            import secrets
            secret = secrets.token_hex(32)
            set_setting('secret_key', secret)
        app.secret_key = secret

    # Start auto-start daemon and health-check daemon
    from app.services.service_manager import start_auto_start_daemon, start_health_check_daemon
    start_auto_start_daemon(app)
    start_health_check_daemon(app)

    # Close DB connections after each request (prevents lingering WAL readers)
    app.teardown_appcontext(lambda exc: close_db())

    # Register SIGTERM handler for graceful docker stop
    signal.signal(signal.SIGTERM, _on_sigterm)
    signal.signal(signal.SIGINT, _on_sigterm)

    return app


def register_blueprints(app):
    """Register all Flask blueprints."""
    from .pages import pages
    from .api_auth import api_auth
    from .api_settings import api_settings
    from .api_subscriptions import api_subscriptions
    from .api_nodes import api_nodes
    from .api_inbounds import api_inbounds
    from .api_outbounds import api_outbounds
    from .api_services import api_services
    from .api_bins import api_bins
    from .api_upgrade import api_upgrade
    from .api_logs import api_logs
    from .api_system import api_system

    app.register_blueprint(pages)
    app.register_blueprint(api_auth)
    app.register_blueprint(api_settings)
    app.register_blueprint(api_subscriptions)
    app.register_blueprint(api_nodes)
    app.register_blueprint(api_inbounds)
    app.register_blueprint(api_outbounds)
    app.register_blueprint(api_services)
    app.register_blueprint(api_bins)
    app.register_blueprint(api_upgrade)
    app.register_blueprint(api_logs)
    app.register_blueprint(api_system)


def is_mobile_device():
    """Detect mobile device from User-Agent header (§ mobile).

    Query-parameter override takes precedence:
      ?mobile=0 → force desktop (persisted in session)
      ?mobile=1 → force mobile  (persisted in session)

    Fallback: regex match against User-Agent.
    """
    mobile_param = request.args.get('mobile')
    if mobile_param == '0':
        session['force_desktop'] = True
        return False
    if mobile_param == '1':
        session.pop('force_desktop', None)
        return True
    if session.get('force_desktop'):
        return False
    ua = request.headers.get('User-Agent', '')
    pattern = (r'(Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|'
               r'Opera Mini|Mobile|CriOS|FxiOS|Silk)')
    return bool(re.search(pattern, ua, re.IGNORECASE))


def auth_required(f):
    """Decorator: enforce session authentication.

    - API routes → 401 JSON
    - Page routes → redirect to /login
    """
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if is_authenticated():
            return f(*args, **kwargs)
        # Detect API vs page request
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        return redirect(url_for('pages.login_page'))
    return decorated
