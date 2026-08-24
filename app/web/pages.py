"""Authenticated desktop pages and mobile SPA route."""

from flask import Blueprint, render_template

from app.web.auth import auth_required

bp = Blueprint('pages', __name__)


@bp.route('/')
@auth_required
def route_page():
    return render_template('route.html', page='route')


@bp.route('/inbounds')
@auth_required
def inbounds_page():
    return render_template('inbounds.html', page='inbounds')


@bp.route('/outbounds')
@auth_required
def outbounds_page():
    return render_template('outbounds.html', page='outbounds')


@bp.route('/subscriptions')
@auth_required
def subscriptions_page():
    return render_template('subscriptions.html', page='subscriptions')


@bp.route('/nodes')
@auth_required
def nodes_page():
    return render_template('nodes.html', page='nodes')


@bp.route('/settings')
@auth_required
def settings_page():
    from app.singbox import get_version

    return render_template(
        'settings.html', page='settings', current_version=get_version()
    )


@bp.route('/logs')
@auth_required
def logs_page():
    return render_template('logs.html', page='logs')


@bp.route('/m')
@auth_required
def mobile_page():
    return render_template('mobile/index.html', page='mobile')
