"""ProxyHub application entry point (§13)."""

from app.routes import create_app
from app.models.setting import get_setting

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        port = int(get_setting('web_port') or 8080)
    app.run(debug=True, host='0.0.0.0', port=port)
