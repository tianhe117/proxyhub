"""Flask control-layer application package.

create_app() factory: registers the API blueprint and initialises the DB.
Auth and template configuration are deferred to the Web/route layer.
"""
from flask import Flask


def create_app() -> Flask:
    """Create and configure the Flask application instance."""
    app = Flask(__name__)
    from app.routes import bp
    app.register_blueprint(bp)
    from app.db.database import init_db
    init_db()
    return app
