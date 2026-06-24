"""Binary status API routes (§4.3)."""

from flask import Blueprint, jsonify

from app.settings import BIN_REGISTRY
from app.process.manager import get_version
from . import auth_required

api_bins = Blueprint('api_bins', __name__, url_prefix='/api/bins')


@api_bins.route('/status', methods=['GET'])
@auth_required
def get_bins_status():
    result = {}
    for name in BIN_REGISTRY:
        result[name] = {
            'version': get_version(name if name != 'sing-box' else name),
            'exe': BIN_REGISTRY[name]['exe'],
        }
    return jsonify(result)
