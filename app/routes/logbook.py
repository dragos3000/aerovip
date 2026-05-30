from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import date, timedelta
from app import db
from app.models import (User, Aircraft, Booking, Setting,
                        LogbookEntry, HOUR_TYPES, PPL_EXERCISES, PPL_EXERCISE_LABELS)

bp = Blueprint('logbook', __name__, url_prefix='/logbook')

EDITOR_ROLES = ('instructor', 'admin', 'manager')


def _can_edit():
    return current_user.role in EDITOR_ROLES


def _to_float(v, default=0.0):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return default


def _to_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _parse_hours(v, default=0.0):
    """Accept 'H:MM' or a decimal number, return decimal hours."""
    v = (v or '').strip()
    if not v:
        return default
    if ':' in v:
        try:
            h, m = v.split(':', 1)
            return round((int(h) if h else 0) + (int(m) if m else 0) / 60.0, 2)
        except (ValueError, TypeError):
            return default
    return _to_float(v, default)


def _form_choices():
    students = User.query.filter_by(role='student', is_active=True).order_by(User.first_name).all()
    instructors = User.query.filter_by(role='instructor', is_active=True).order_by(User.first_name).all()
    aircraft = Aircraft.query.order_by(Aircraft.registration).all()
    return students, instructors, aircraft


@bp.route('/')
@login_required
def index():
    q = LogbookEntry.query
    if current_user.role == 'student':
        q = q.filter_by(student_id=current_user.id)
    elif current_user.role == 'instructor':
        q = q.filter_by(instructor_id=current_user.id)

    # Editors (admin/manager/instructor) can filter the logbook by student.
    students = []
    selected_student = None
    if _can_edit():
        students = User.query.filter_by(role='student', is_active=True).order_by(User.first_name).all()
        sid = request.args.get('student_id')
        if sid and sid.isdigit():
            selected_student = int(sid)
            q = q.filter(LogbookEntry.student_id == selected_student)

    # Period filter
    selected_period = request.args.get('period', 'all')
    today = date.today()
    start = None
    if selected_period == '30d':
        start = today - timedelta(days=30)
    elif selected_period == '90d':
        start = today - timedelta(days=90)
    elif selected_period == 'month':
        start = today.replace(day=1)
    elif selected_period == 'year':
        start = today.replace(month=1, day=1)
    if start:
        q = q.filter(LogbookEntry.flight_date >= start)

    entries = q.order_by(LogbookEntry.flight_date.desc(), LogbookEntry.id.desc()).all()

    totals = {
        'total': sum(e.total_time or 0 for e in entries),
        'dual': sum(e.dual_time or 0 for e in entries),
        'pic': sum(e.pic_time or 0 for e in entries),
        'ldg_day': sum(e.landings_day or 0 for e in entries),
        'ldg_night': sum(e.landings_night or 0 for e in entries),
    }
    return render_template('logbook/list.html', entries=entries, totals=totals,
                           can_edit=_can_edit(), students=students, selected_student=selected_student,
                           selected_period=selected_period, exercise_labels=PPL_EXERCISE_LABELS)


@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if not _can_edit():
        flash('Only instructors can add logbook entries.', 'danger')
        return redirect(url_for('logbook.index'))

    students, instructors, aircraft = _form_choices()

    if request.method == 'POST':
        return _save(LogbookEntry(), students, instructors, aircraft)

    # Pre-fill from a finished booking if provided
    entry = LogbookEntry(
        instructor_id=current_user.id if current_user.role == 'instructor' else None,
        flight_date=date.today(),
        hour_type='PPL-A',
        dep_place=Setting.get('icao_airport', 'LROP'),
        arr_place=Setting.get('icao_airport', 'LROP'),
    )
    booking_id = request.args.get('booking_id')
    if booking_id:
        b = db.session.get(Booking, _to_int(booking_id, 0))
        if b:
            entry.student_id = b.student_id
            entry.instructor_id = b.instructor_id
            entry.aircraft_id = b.aircraft_id
            entry.booking_id = b.id
            entry.flight_date = b.start_time.date()
            entry.dep_time = b.start_time.strftime('%H:%M')
            entry.arr_time = b.end_time.strftime('%H:%M')
            entry.hour_type = b.hour_type
            entry.total_time = round(b.duration_hours, 1)
            entry.dual_time = round(b.duration_hours, 1)

    return render_template('logbook/form.html', entry=entry, students=students,
                           instructors=instructors, aircraft=aircraft,
                           hour_types=HOUR_TYPES, exercises=PPL_EXERCISES,
                           selected_ex=set(), title='add')


@bp.route('/<int:entry_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(entry_id):
    entry = db.session.get(LogbookEntry, entry_id)
    if not entry:
        flash('Logbook entry not found.', 'danger')
        return redirect(url_for('logbook.index'))
    if not _can_edit() or (current_user.role == 'instructor' and entry.instructor_id != current_user.id):
        flash('You cannot edit this entry.', 'danger')
        return redirect(url_for('logbook.index'))

    students, instructors, aircraft = _form_choices()
    if request.method == 'POST':
        return _save(entry, students, instructors, aircraft)

    return render_template('logbook/form.html', entry=entry, students=students,
                           instructors=instructors, aircraft=aircraft,
                           hour_types=HOUR_TYPES, exercises=PPL_EXERCISES,
                           selected_ex=set(entry.exercise_codes), title='edit')


@bp.route('/<int:entry_id>/delete', methods=['POST'])
@login_required
def delete(entry_id):
    entry = db.session.get(LogbookEntry, entry_id)
    if entry and (_can_edit() and (current_user.role != 'instructor' or entry.instructor_id == current_user.id)):
        db.session.delete(entry)
        db.session.commit()
        flash('Logbook entry deleted.', 'success')
    return redirect(url_for('logbook.index'))


def _save(entry, students, instructors, aircraft):
    f = request.form
    student_id = _to_int(f.get('student_id'), 0)
    if not student_id:
        flash('Please choose a student.', 'danger')
        return render_template('logbook/form.html', entry=entry, students=students,
                               instructors=instructors, aircraft=aircraft,
                               hour_types=HOUR_TYPES, exercises=PPL_EXERCISES,
                               selected_ex=set(f.getlist('exercises')),
                               title='edit' if entry.id else 'add')
    try:
        entry.flight_date = date.fromisoformat(f.get('flight_date'))
    except (TypeError, ValueError):
        entry.flight_date = date.today()

    entry.student_id = student_id
    entry.instructor_id = _to_int(f.get('instructor_id')) or None
    entry.aircraft_id = _to_int(f.get('aircraft_id')) or None
    entry.dep_place = (f.get('dep_place') or '').strip().upper()
    entry.arr_place = (f.get('arr_place') or '').strip().upper()
    entry.dep_time = (f.get('dep_time') or '').strip()
    entry.arr_time = (f.get('arr_time') or '').strip()
    entry.hour_type = f.get('hour_type') if f.get('hour_type') in HOUR_TYPES else 'PPL-A'
    entry.total_time = _parse_hours(f.get('total_time'))
    entry.dual_time = _parse_hours(f.get('dual_time'))
    entry.pic_time = _parse_hours(f.get('pic_time'))
    entry.landings_day = _to_int(f.get('landings_day'))
    entry.landings_night = _to_int(f.get('landings_night'))
    # exercises only apply to PPL-A
    ex = f.getlist('exercises') if entry.hour_type == 'PPL-A' else []
    valid = {code for code, _ in PPL_EXERCISES}
    entry.exercises = ','.join(c for c in ex if c in valid)
    entry.remarks = (f.get('remarks') or '').strip()

    if not entry.id:
        db.session.add(entry)
    db.session.commit()
    flash('Logbook entry saved.', 'success')
    return redirect(url_for('logbook.index'))
