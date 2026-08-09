"""ProxyHub application entry point (§13)."""

import os
import signal
import threading

from app.routes import create_app
from app.models.setting import get_setting


def _graceful_shutdown():
    """Clean shutdown: stop daemon, flush logs, checkpoint DB."""
    try:
        from app.services.service_manager import stop_health_check_daemon
        stop_health_check_daemon()
    except Exception:
        pass
    try:
        from app.logger import web_logger
        web_logger.restore()
    except Exception:
        pass
    try:
        from app.models.database import get_db, close_db
        db = get_db()
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.commit()
        close_db()
    except Exception:
        pass
    print('[shutdown] graceful shutdown complete')


def _on_sigterm(_signum, _frame):
    """Handle docker stop / SIGTERM — do cleanup in a thread so we don't block."""
    t = threading.Thread(target=_graceful_shutdown, daemon=True)
    t.start()
    t.join(timeout=5)
    os._exit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, _on_sigterm)
    signal.signal(signal.SIGINT, _on_sigterm)

    app = create_app()
    with app.app_context():
        port = int(get_setting('web_port') or 8080)
    app.run(debug=True, host='0.0.0.0', port=port)
