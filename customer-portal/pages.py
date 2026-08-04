import os
from flask import Blueprint, redirect, render_template, url_for

from auth import load_session

DEBUG = os.environ.get('DEBUG', '').lower() in ('true', '1', 'yes')

pages_bp = Blueprint('pages', __name__, template_folder='templates')


@pages_bp.route('/customer/login')
def login():
    return render_template('customer/login.html', debug=DEBUG)


@pages_bp.route('/customer/logout')
def logout():
    resp = redirect(url_for('pages.login'))
    resp.headers['Cache-Control'] = 'no-store'
    resp.delete_cookie('billing_session', path='/customer/')
    return resp


@pages_bp.route('/customer/')
def app_shell():
    return render_template('customer/app.html')


@pages_bp.route('/customer/maintenance')
def maintenance():
    if not load_session():
        return redirect(url_for('pages.login'))
    return render_template('customer/maintenance.html')


@pages_bp.route('/customer/report')
def report():
    if not load_session():
        return redirect(url_for('pages.login'))
    return render_template('customer/report.html')


@pages_bp.route('/customer/billing/<int:customer_number>')
def billing_redirect(customer_number):
    return redirect(url_for('pages.app_shell'), code=301)


@pages_bp.route('/customer/identify')
def identify_redirect():
    return redirect(url_for('pages.login'), code=301)
