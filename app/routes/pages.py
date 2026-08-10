"""Page routes (§4.1)."""

from flask import Blueprint, render_template, redirect, url_for, request

from app.services.auth_service import is_authenticated, login, logout
from . import auth_required, is_mobile_device

pages = Blueprint('pages', __name__)

MOBILE_TEMPLATE_MAP = {
    'dashboard': 'mobile/dashboard.html',
    'inbounds': 'mobile/inbounds.html',
    'outbounds': 'mobile/outbounds.html',
}


def _render_page(template_name, desktop_template, **kwargs):
    """Render desktop or mobile template based on device detection."""
    if is_mobile_device() and template_name in MOBILE_TEMPLATE_MAP:
        return render_template(MOBILE_TEMPLATE_MAP[template_name], **kwargs)
    return render_template(desktop_template, **kwargs)


@pages.route('/')
def index():
    return redirect(url_for('pages.dashboard'))


@pages.route('/dashboard')
@auth_required
def dashboard():
    return _render_page('dashboard', 'dashboard.html', page='dashboard')


@pages.route('/inbounds')
@auth_required
def inbounds_page():
    return _render_page('inbounds', 'inbounds.html', page='inbounds')


@pages.route('/outbounds')
@auth_required
def outbounds_page():
    return _render_page('outbounds', 'outbounds.html', page='outbounds')


@pages.route('/subscriptions')
@auth_required
def subscriptions_page():
    return render_template('subscriptions.html', page='subscriptions')


@pages.route('/nodes')
@auth_required
def nodes_page():
    return render_template('nodes.html', page='nodes')


@pages.route('/settings')
@auth_required
def settings_page():
    return render_template('settings.html', page='settings')


@pages.route('/login', methods=['GET', 'POST'])
def login_page():
    if is_authenticated():
        return redirect(url_for('pages.dashboard'))
    error = None
    if request.method == 'POST':
        ok, error = login(
            request.form.get('username', ''),
            request.form.get('password', '')
        )
        if ok:
            return redirect(url_for('pages.dashboard'))
    if is_mobile_device():
        return render_template('mobile/login.html', error=error)
    return render_template('login.html', error=error)


@pages.route('/logout')
def logout_page():
    logout()
    return redirect(url_for('pages.login_page'))
