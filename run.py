"""ProxyHub v2 single entry point (shared by venv / docker)."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # Debug mode disabled by default to avoid multiple workers in production.
    # Enable only during development: app.run(debug=True)
    app.run(host="0.0.0.0", port=8080, debug=False)
