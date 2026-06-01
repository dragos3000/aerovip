from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from app import db
from app.models import User, Booking, Aircraft, Setting
from app.forms import UserEditForm, SettingsForm
from app.airfield import get_airfield_info, save_airfield_info, get_airfield_map_url

bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.role != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated


def settings_required(f):
    """Settings is open to planners (admins + managers); API keys/URLs stay admin-only."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_planner:
            flash('Settings access required.', 'danger')
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
@settings_required
def settings():
    from app import operating
    form = SettingsForm()
    # API keys / URLs are admin-only; managers never see or save them.
    can_edit_api = (current_user.role == 'admin')

    if form.validate_on_submit():
        if can_edit_api:
            Setting.set('checkwx_api_key', form.checkwx_api_key.data.strip(),
                         'CheckWX API key for weather and NOTAMs')
            Setting.set('airfield_weather_url', form.airfield_weather_url.data.strip(),
                         'Airfield weather station JSON URL')
        Setting.set('icao_airport', form.icao_airport.data.strip().upper() or 'LRBS',
                     'ICAO airport code for weather/NOTAMs')
        # Operating window (UTC) + operating week days — available to managers too.
        start = form.op_hours_start_utc.data if form.op_hours_start_utc.data is not None else operating.DEFAULT_START_UTC
        end = form.op_hours_end_utc.data if form.op_hours_end_utc.data is not None else operating.DEFAULT_END_UTC
        if end <= start:
            end = start + 1
        Setting.set(operating.OP_START_KEY, str(start), 'Airfield operating start hour (UTC)')
        Setting.set(operating.OP_END_KEY, str(end), 'Airfield operating end hour (UTC, exclusive)')
        for wd, abbr in enumerate(operating.DAY_ABBR):
            field = getattr(form, 'op_day_' + abbr)
            Setting.set(operating.DAY_SETTING_KEYS[wd], '1' if field.data else '0',
                        'Airfield operates on ' + abbr.capitalize())
        save_airfield_info(request.form)
        # Apply the new weather config soon, in the background (don't block the save on a slow API).
        from flask import current_app
        from app.weather_cache import refresh_now_async
        refresh_now_async(current_app._get_current_object())
        flash('Settings saved successfully.', 'success')
        return redirect(url_for('admin.settings'))

    # Pre-fill form with current values
    form.checkwx_api_key.data = Setting.get('checkwx_api_key', '')
    form.icao_airport.data = Setting.get('icao_airport', 'LRBS')
    form.airfield_weather_url.data = Setting.get('airfield_weather_url', '')
    start_utc, end_utc = operating.operating_hours_utc()
    form.op_hours_start_utc.data = start_utc
    form.op_hours_end_utc.data = end_utc
    open_days = operating.open_days_map()
    for wd, abbr in enumerate(operating.DAY_ABBR):
        getattr(form, 'op_day_' + abbr).data = open_days[wd]

    return render_template('admin/settings.html', form=form,
                           can_edit_api=can_edit_api,
                           airfield_info=get_airfield_info(),
                           airfield_map_url=get_airfield_map_url('ro'),
                           airfield_map_url_en=get_airfield_map_url('en'))
