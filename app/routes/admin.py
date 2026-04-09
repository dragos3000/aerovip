from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from app import db
from app.models import User, Booking, Aircraft, Setting
from app.forms import UserEditForm, SettingsForm

bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.role != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated


@bp.route('/users')
@login_required
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=all_users)


@bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin.users'))

    form = UserEditForm(obj=user)
    if form.validate_on_submit():
        user.email = form.email.data.lower()
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        user.phone = form.phone.data
        user.role = form.role.data
        user.is_active = form.is_active.data
        db.session.commit()
        flash('User updated successfully.', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/edit_user.html', form=form, user=user)


@bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    user = db.session.get(User, user_id)
    if user and user.id != current_user.id:
        user.is_active = not user.is_active
        db.session.commit()
        status = 'activated' if user.is_active else 'deactivated'
        flash(f'User {user.full_name} {status}.', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/bookings')
@login_required
@admin_required
def all_bookings():
    bookings = Booking.query.order_by(Booking.start_time.desc()).all()
    return render_template('admin/bookings.html', bookings=bookings)


@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    form = SettingsForm()

    if form.validate_on_submit():
        Setting.set('checkwx_api_key', form.checkwx_api_key.data.strip(),
                     'CheckWX API key for weather and NOTAMs')
        Setting.set('icao_airport', form.icao_airport.data.strip().upper() or 'LRBS',
                     'ICAO airport code for weather/NOTAMs')
        Setting.set('airfield_weather_url', form.airfield_weather_url.data.strip(),
                     'Airfield weather station JSON URL')
        flash('Settings saved successfully.', 'success')
        return redirect(url_for('admin.settings'))

    # Pre-fill form with current values
    form.checkwx_api_key.data = Setting.get('checkwx_api_key', '')
    form.icao_airport.data = Setting.get('icao_airport', 'LRBS')
    form.airfield_weather_url.data = Setting.get('airfield_weather_url', '')

    return render_template('admin/settings.html', form=form)
