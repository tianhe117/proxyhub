"""Authentication: auth_required decorator + login/logout routes.

Password empty (web_password == '') → auth disabled, everything passes.
Session-based; API routes get 401 JSON, page routes get redirected to /login.
"""

import functools

from flask import Blueprint, redirect, request, session, jsonify, render_template, url_for

from app.settings import get_setting

bp = Blueprint('auth', __name__)


def _auth_disabled():
    return not get_setting('web_password')


def _is_api_request():
    return request.path.startswith('/api/')


def _safe_next(target):
    """Only allow in-site paths (prevent open redirect)."""
    if target and target.startswith('/') and not target.startswith('//'):
        return target
    return '/'


def auth_required(view):
    """Gate a view behind session auth (no-op when password is empty)."""
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if _auth_disabled() or session.get('authenticated'):
            return view(*args, **kwargs)
        if _is_api_request():
            return jsonify({'success': False, 'message': 'unauthorized'}), 401
        return redirect(url_for('auth.login', next=request.path))
    return wrapper


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if _auth_disabled():
        return redirect('/')
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if (username == get_setting('web_username')
                and password == get_setting('web_password')):
            session['authenticated'] = True
            return redirect(_safe_next(request.args.get('next')))
        error = 'Invalid username or password'
    return render_template('login.html', error=error)


@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
