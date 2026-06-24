"""Session-based authentication (§5.1)."""

from flask import session

from app.models.setting import get_setting


def is_authenticated():
    """Return True if the current session is authenticated or auth is disabled."""
    password = get_setting('web_password')
    # Empty password = authentication disabled
    if not password:
        return True
    return session.get('authenticated', False)


def login(username, password):
    """Validate credentials and mark the session as authenticated.

    Returns (success: bool, error_message: str).
    """
    cfg_user = get_setting('web_username') or 'admin'
    cfg_pass = get_setting('web_password') or ''

    if username == cfg_user and password == cfg_pass:
        session.permanent = True
        session['authenticated'] = True
        return True, ''
    return False, 'Invalid username or password'


def logout():
    """Clear the authentication flag from the session."""
    session.pop('authenticated', None)
