"""Flask control-layer application package.

create_app() factory: registers the API blueprint and initialises the DB.
Auth and template configuration are deferred to the Web/route layer.
"""
import os

from flask import Flask

from app import config


def _load_secret_key():
    """Session secret: env override, else persisted random file (survives restarts)."""
    env = os.environ.get('PROXYHUB_SECRET')
    if env:
        return env
    path = os.path.join(config.DATA_DIR, 'secret_key')
    try:
        with open(path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        pass
    secret = os.urandom(32).hex()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(secret)
    os.chmod(path, 0o600)
    return secret


def create_app(config_overrides=None) -> Flask:
    """Create and configure the Flask application instance."""
    config.configure(config_overrides)

    from app import settings
    from app.logger import init_logger

    settings.configure()
    init_logger()

    app = Flask(
        __name__,
        template_folder='../templates',
        static_folder='../static',
    )
    app.config.update({
        'BASE_DIR': config.BASE_DIR,
        'DATA_DIR': config.DATA_DIR,
        'LOGS_DIR': config.LOGS_DIR,
        'DB_PATH': config.DB_PATH,
        'CONFIG_PATH': config.CONFIG_PATH,
    })
    app.secret_key = _load_secret_key()

    from app.web.api import bp as api_bp
    from app.web.auth import bp as auth_bp
    from app.web.pages import bp as pages_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)

    from app.db.database import close_db, init_db

    close_db()
    init_db()

    @app.teardown_appcontext
    def _close_database(_error):
        close_db()

    return app
