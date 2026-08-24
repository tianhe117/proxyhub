"""Flask control-layer application package.

create_app() factory: registers the API blueprint and initialises the DB.
Auth and template configuration are deferred to the Web/route layer.
"""
import os

from flask import Flask

from app import settings


def _load_secret_key():
    """Session secret: env override, else persisted random file (survives restarts)."""
    env = os.environ.get('PROXYHUB_SECRET')
    if env:
        return env
    path = os.path.join(settings.DATA_DIR, 'secret_key')
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


def create_app() -> Flask:
    """Create and configure the Flask application instance."""
    app = Flask(__name__, template_folder='../templates')
    app.secret_key = _load_secret_key()

    from app.routes import bp as api_bp
    from app.auth import bp as auth_bp
    from app.pages import bp as pages_bp
    from app.auth import auth_required

    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    api_bp.before_request(auth_required(lambda: None))
    app.register_blueprint(api_bp)

    from app.db.database import init_db
    init_db()
    return app
