from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort, session
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from functools import wraps
from app import db
from app.models import User, Aircraft, Booking, HOUR_TYPES
from app.models import AvailabilitySubmission, AvailabilitySlot, FlightRequest
from app import weekutils
from app.translations import get_translation


def _t(key):
    return get_translation(key, session.get('lang', 'ro'))

bp = Blueprint('scheduling', __name__, url_prefix='/schedule')


def planner_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_planner:
            flash('Scheduling access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated


def _resolve_week(default='next'):
    """Read ?week=YYYY-Www from the query string, falling back to next/current week."""
    parsed = weekutils.parse_week_key(request.args.get('week'))
    if parsed:
        return parsed
    return weekutils.next_iso() if default == 'next' else weekutils.current_iso()


@bp.route('/')
@login_required
def index():
    """Send each role to its natural landing page."""
    if current_user.is_planner:
        return redirect(url_for('scheduling.plan'))
    if current_user.role == 'student':
        return redirect(url_for('scheduling.availability'))
    return redirect(url_for('scheduling.my_schedule'))


# ---------------------------------------------------------------------------
# Student: submit availability
# ---------------------------------------------------------------------------
@bp.route('/availability')
@login_required
def availability():
    if current_user.role != 'student':
        return redirect(url_for('scheduling.index'))

    iso_year, iso_week = _resolve_week('next')
    week = weekutils.week_context(iso_year, iso_week)

    submission = AvailabilitySubmission.query.filter_by(
        student_id=current_user.id, iso_year=iso_year, iso_week=iso_week
    ).first()

    existing_slots = []
    existing_requests = []
    notes = ''
    if submission:
        existing_slots = [f"{s.slot_date.isoformat()}|{s.hour}" for s in submission.slots]
        existing_requests = [{'hour_type': r.hour_type, 'hours': r.hours} for r in submission.requests]
        notes = submission.notes or ''

    return render_template(
        'scheduling/availability.html',
        week=week,
        hours=list(range(weekutils.GRID_START_HOUR, weekutils.GRID_END_HOUR)),
        hour_types=HOUR_TYPES,
        existing_slots=existing_slots,
        existing_requests=existing_requests,
        notes=notes,
        upcoming_weeks=weekutils.upcoming_weeks(6),
    )


@bp.route('/availability', methods=['POST'])
@login_required
def save_availability():
    if current_user.role != 'student':
        return jsonify({'ok': False, 'error': 'Only students submit availability.'}), 403

    data = request.get_json(silent=True) or {}
    parsed = weekutils.parse_week_key(data.get('week'))
    if not parsed:
        return jsonify({'ok': False, 'error': 'Invalid week.'}), 400
    iso_year, iso_week = parsed

    # Only allow current week onwards (no editing the past).
    cur_y, cur_w = weekutils.current_iso()
    if (iso_year, iso_week) < (cur_y, cur_w):
        return jsonify({'ok': False, 'error': 'Cannot submit availability for a past week.'}), 400

    valid_dates = {d.isoformat() for d in weekutils.week_dates(iso_year, iso_week)}

    submission = AvailabilitySubmission.query.filter_by(
        student_id=current_user.id, iso_year=iso_year, iso_week=iso_week
    ).first()
    if not submission:
        submission = AvailabilitySubmission(
            student_id=current_user.id, iso_year=iso_year, iso_week=iso_week
        )
        db.session.add(submission)
        db.session.flush()

    # Replace slots.
    AvailabilitySlot.query.filter_by(submission_id=submission.id).delete()
    seen = set()
    for slot in data.get('slots', []):
        d = slot.get('date')
        h = slot.get('hour')
        if d not in valid_dates:
            continue
        try:
            h = int(h)
        except (TypeError, ValueError):
            continue
        if not (0 <= h <= 23):
            continue
        key = (d, h)
        if key in seen:
            continue
        seen.add(key)
        db.session.add(AvailabilitySlot(
            submission_id=submission.id,
            slot_date=date.fromisoformat(d),
            hour=h,
        ))

    # Replace flight requests.
    FlightRequest.query.filter_by(submission_id=submission.id).delete()
    for req in data.get('requests', []):
        htype = req.get('hour_type')
        if htype not in HOUR_TYPES:
            continue
        try:
            hours = float(req.get('hours'))
        except (TypeError, ValueError):
            continue
        if hours <= 0:
            continue
        db.session.add(FlightRequest(
            submission_id=submission.id, hour_type=htype, hours=round(hours, 1)
        ))

    submission.notes = (data.get('notes') or '').strip()
    db.session.commit()
    return jsonify({'ok': True, 'slot_count': len(seen)})


# ---------------------------------------------------------------------------
# Student / Instructor: my schedule (assigned flights)
# ---------------------------------------------------------------------------
@bp.route('/my')
@login_required
def my_schedule():
    if current_user.is_planner:
        return redirect(url_for('scheduling.plan'))

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    q = Booking.query.filter(Booking.status != 'cancelled', Booking.end_time >= today)
    if current_user.role == 'instructor':
        q = q.filter(Booking.instructor_id == current_user.id)
    else:
        q = q.filter(Booking.student_id == current_user.id)
    bookings = q.order_by(Booking.start_time).all()

    return render_template('scheduling/my_schedule.html', bookings=bookings)


# ---------------------------------------------------------------------------
# Planner: weekly planning board
# ---------------------------------------------------------------------------
def _booking_dict(b):
    # A flight ending at midnight is shown as 24:00 (not 00:00) so it fills the 23:00 row.
    end_hour = b.end_time.hour + (24 if b.end_time.date() > b.start_time.date() else 0)
    return {
        'id': b.id,
        'student_id': b.student_id,
        'student': b.student.full_name,
        'date': b.start_time.date().isoformat(),
        'start': b.start_time.strftime('%H:%M'),
        'end': f'{end_hour:02d}:{b.end_time.minute:02d}',
        'instructor_id': b.instructor_id,
        'instructor': b.instructor.full_name,
        'aircraft_id': b.aircraft_id,
        'aircraft': b.aircraft.registration,
        'hour_type': b.hour_type,
        'hours': round(b.duration_hours, 1),
        'notes': b.notes or '',
    }


@bp.route('/plan')
@login_required
@planner_required
def plan():
    iso_year, iso_week = _resolve_week('next')
    week = weekutils.week_context(iso_year, iso_week)
    days = weekutils.week_dates(iso_year, iso_week)
    week_start = datetime.combine(days[0], datetime.min.time())
    week_end = datetime.combine(days[6] + timedelta(days=1), datetime.min.time())

    submissions = AvailabilitySubmission.query.filter_by(
        iso_year=iso_year, iso_week=iso_week
    ).all()

    # All bookings that fall in this week.
    week_bookings = Booking.query.filter(
        Booking.status != 'cancelled',
        Booking.start_time >= week_start,
        Booking.start_time < week_end,
    ).all()

    bookings_by_aircraft = {}
    assigned_hours = {}
    for b in week_bookings:
        bookings_by_aircraft.setdefault(b.aircraft_id, []).append(_booking_dict(b))
        assigned_hours[b.student_id] = assigned_hours.get(b.student_id, 0) + b.duration_hours

    # One grid per aircraft (the planning resource).
    aircraft = []
    for a in Aircraft.query.filter_by(is_available=True).order_by(Aircraft.registration).all():
        aircraft.append({
            'id': a.id,
            'registration': a.registration,
            'model': a.model,
            'bookings': sorted(bookings_by_aircraft.get(a.id, []), key=lambda x: (x['date'], x['start'])),
        })

    # Students who submitted availability — used for the assign dropdown + helper.
    students = []
    for sub in submissions:
        slots_by_day = {}
        for s in sub.slots:
            slots_by_day.setdefault(s.slot_date.isoformat(), []).append(s.hour)
        students.append({
            'id': sub.student_id,
            'name': sub.student.full_name,
            'requests': [{'hour_type': r.hour_type, 'hours': r.hours} for r in sub.requests],
            'requested_hours': round(sub.total_requested_hours, 1),
            'assigned_hours': round(assigned_hours.get(sub.student_id, 0), 1),
            'slots_by_day': {d: sorted(hs) for d, hs in slots_by_day.items()},
        })
    students.sort(key=lambda s: s['name'])

    instructors = [{'id': i.id, 'name': i.full_name}
                   for i in User.query.filter_by(role='instructor', is_active=True).order_by(User.first_name).all()]

    tz_mode = session.get('tz', 'lt')
    disp_shift = weekutils.utc_shift_hours(days[0]) if tz_mode == 'utc' else 0

    return render_template(
        'scheduling/plan.html',
        week=week,
        hours=list(range(weekutils.GRID_START_HOUR, weekutils.GRID_END_HOUR)),
        hour_types=HOUR_TYPES,
        aircraft=aircraft,
        students=students,
        instructors=instructors,
        disp_shift=disp_shift,
    )


@bp.route('/plan/assign', methods=['POST'])
@login_required
@planner_required
def assign():
    data = request.get_json(silent=True) or {}
    try:
        student_id = int(data['student_id'])
        instructor_id = int(data['instructor_id'])
        aircraft_id = int(data['aircraft_id'])
        slot_date = date.fromisoformat(data['date'])
        start_h, start_m = (int(x) for x in data['start'].split(':'))
        end_h, end_m = (int(x) for x in data['end'].split(':'))
    except (KeyError, ValueError, TypeError):
        return jsonify({'ok': False, 'error': _t('err.invalid_fields')}), 400

    hour_type = data.get('hour_type')
    if hour_type not in HOUR_TYPES:
        return jsonify({'ok': False, 'error': _t('err.invalid_type')}), 400

    start_time = datetime.combine(slot_date, datetime.min.time()).replace(hour=start_h, minute=start_m)
    if end_h == 24:
        end_time = datetime.combine(slot_date, datetime.min.time()) + timedelta(days=1)
    else:
        end_time = datetime.combine(slot_date, datetime.min.time()).replace(hour=end_h, minute=end_m)
    if end_time <= start_time:
        return jsonify({'ok': False, 'error': _t('err.end_after_start')}), 400

    booking_id = data.get('booking_id')
    exclude_id = int(booking_id) if booking_id else None

    conflict = Booking.has_conflict(
        aircraft_id=aircraft_id, instructor_id=instructor_id, student_id=student_id,
        start_time=start_time, end_time=end_time, exclude_id=exclude_id,
    )
    if conflict:
        return jsonify({'ok': False, 'error': _t(conflict)}), 409

    # Does the assignment fall within the student's submitted availability?
    iso = slot_date.isocalendar()
    sub = AvailabilitySubmission.query.filter_by(
        student_id=student_id, iso_year=iso[0], iso_week=iso[1]
    ).first()
    covered = set()
    if sub:
        covered = {(s.slot_date, s.hour) for s in sub.slots}
    within = all((slot_date, h) in covered for h in range(start_h, end_h))

    # Don't allow scheduling more hours than the student requested for the week.
    new_duration = (end_time - start_time).total_seconds() / 3600.0
    requested = sum(r.hours for r in sub.requests) if sub else 0.0
    days = weekutils.week_dates(iso[0], iso[1])
    wk_start = datetime.combine(days[0], datetime.min.time())
    wk_end = datetime.combine(days[6] + timedelta(days=1), datetime.min.time())
    assigned_q = Booking.query.filter(
        Booking.student_id == student_id,
        Booking.status != 'cancelled',
        Booking.start_time >= wk_start,
        Booking.start_time < wk_end,
    )
    if exclude_id:
        assigned_q = assigned_q.filter(Booking.id != exclude_id)
    already = sum((b.end_time - b.start_time).total_seconds() / 3600.0 for b in assigned_q.all())
    if already + new_duration > requested + 1e-6:
        remaining = max(0.0, requested - already)
        return jsonify({
            'ok': False,
            'error': _t('err.exceeds_hours').format(
                requested=f'{requested:g}', already=f'{already:g}',
                remaining=f'{remaining:g}', duration=f'{new_duration:g}')
        }), 400

    if exclude_id:
        booking = db.session.get(Booking, exclude_id)
        if not booking:
            return jsonify({'ok': False, 'error': _t('err.not_found')}), 404
        booking.student_id = student_id
        booking.instructor_id = instructor_id
        booking.aircraft_id = aircraft_id
        booking.start_time = start_time
        booking.end_time = end_time
        booking.hour_type = hour_type
        booking.notes = (data.get('notes') or '').strip()
    else:
        booking = Booking(
            student_id=student_id, instructor_id=instructor_id, aircraft_id=aircraft_id,
            start_time=start_time, end_time=end_time, hour_type=hour_type,
            flight_type='training', status='confirmed', notes=(data.get('notes') or '').strip(),
        )
        db.session.add(booking)
    db.session.commit()

    return jsonify({'ok': True, 'booking': _booking_dict(booking), 'within_availability': within})


@bp.route('/<int:booking_id>/cancel', methods=['POST'])
@login_required
@planner_required
def cancel(booking_id):
    """Cancel a booking from a normal form (e.g. the admin All Bookings list)."""
    booking = db.session.get(Booking, booking_id)
    if not booking:
        flash('Booking not found.', 'danger')
    else:
        booking.status = 'cancelled'
        db.session.commit()
        flash('Booking cancelled.', 'success')
    return redirect(request.referrer or url_for('scheduling.plan'))


@bp.route('/plan/booking/<int:booking_id>/delete', methods=['POST'])
@login_required
@planner_required
def delete_booking(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({'ok': False, 'error': 'Booking not found.'}), 404
    db.session.delete(booking)
    db.session.commit()
    return jsonify({'ok': True})
