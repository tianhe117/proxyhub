"""Flask control-layer application package.

The create_app() factory lives here; blueprint registration, auth, and
template configuration are deferred to the Web/route layer.
"""
from flask import Flask


def create_app() -> Flask:
    """Create and configure the Flask application instance."""
    app = Flask(__name__)
    # TODO(Web/route layer): register routes blueprint, auth_required, template paths.
    return app
