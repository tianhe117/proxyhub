"""Log API routes (§4.10)."""

from flask import Blueprint, request, jsonify

from app.logger import web_logger
from . import auth_required

api_logs = Blueprint('api_logs', __name__, url_prefix='/api/logs')


@api_logs.route('/', methods=['GET'])
@auth_required
def get_logs():
    since = request.args.get('since', 0, type=int)
    entries, total = web_logger.get_logs(since)
    return jsonify({'logs': entries, 'total': total})
