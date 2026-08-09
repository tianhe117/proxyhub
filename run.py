"""ProxyHub application entry point."""

from app.routes import create_app
from app.models.setting import get_setting
import os

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        port = int(get_setting('web_port') or 8080)
    debug = os.getenv('DEBUG', 'TRUE') == 'TRUE'
    app.run(debug=debug, host='0.0.0.0', port=port)
