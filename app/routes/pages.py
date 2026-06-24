"""Page routes (§4.1)."""

from flask import Blueprint, render_template, redirect, url_for, request

from app.services.auth_service import is_authenticated, login, logout
from . import auth_required

pages = Blueprint('pages', __name__)


@pages.route('/')
def index():
    return redirect(url_for('pages.dashboard'))


@pages.route('/dashboard')
@auth_required
def dashboard():
    return render_template('dashboard.html', page='dashboard')


@pages.route('/inbounds')
@auth_required
def inbounds_page():
    return render_template('inbounds.html', page='inbounds')


@pages.route('/outbounds')
@auth_required
def outbounds_page():
    return render_template('outbounds.html', page='outbounds')


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
    return render_template('login.html', error=error)


@pages.route('/logout')
def logout_page():
    logout()
    return redirect(url_for('pages.login_page'))
