"""Shared API blueprint, split into business-domain route modules."""

from flask import Blueprint

from app.web.auth import auth_required

bp = Blueprint('api', __name__)
bp.before_request(auth_required(lambda: None))

# Import modules after creating bp so decorators register on the shared blueprint.
from app.web.api import nodes, routing, runtime, settings, subscriptions  # noqa: E402,F401
