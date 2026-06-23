"""Route registration, Flask application factory, and authentication decorator (§13, §5.1).

Each API route handler must be ≤ 10 lines (§8.1).
"""

import os

from flask import Flask, redirect, url_for, session, jsonify, request

from app.services.auth_service import is_authenticated


def create_app():
    """Create and configure the Flask application."""
    import os as _os
    from datetime import timedelta
    _base = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    app = Flask(__name__, template_folder=_os.path.join(_base, 'templates'))

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
    from app.models.database import init_db
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

    # Start auto-start daemon
    from app.services.service_manager import start_auto_start_daemon
    start_auto_start_daemon(app)

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
