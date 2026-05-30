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

    # Night begins at sunset (per day) — used to shade the night window on the grid.
    from app.sun import sunset_local
    night_start = {}
    for d in week['days']:
        ss = sunset_local(d)
        night_start[d.isoformat()] = (ss.hour + (1 if ss.minute else 0)) if ss else 99

    return render_template(
        'scheduling/availability.html',
        week=week,
        hours=list(range(weekutils.GRID_START_HOUR, weekutils.GRID_END_HOUR)),
        hour_types=HOUR_TYPES,
        existing_slots=existing_slots,
        existing_requests=existing_requests,
        notes=notes,
        night_start=night_start,
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

    # If Night hours are requested, require at least one availability slot after sunset.
    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0
    # PPL-A (unlicensed training) can't be mixed with the licensed types.
    req_types = {r.get('hour_type') for r in data.get('requests', [])
                 if r.get('hour_type') in HOUR_TYPES and _num(r.get('hours')) > 0}
    if 'PPL-A' in req_types and (req_types - {'PPL-A'}):
        return jsonify({'ok': False, 'error': _t('err.ppl_exclusive')}), 400

    wants_night = any(r.get('hour_type') == 'Night' and _num(r.get('hours')) > 0
                      for r in data.get('requests', []))
    if wants_night:
        from app.sun import sunset_local
        night_start = {}
        for d in weekutils.week_dates(iso_year, iso_week):
            ss = sunset_local(d)
            night_start[d.isoformat()] = (ss.hour + (1 if ss.minute else 0)) if ss else 99
        has_night = False
        for slot in data.get('slots', []):
            try:
                h = int(slot.get('hour'))
            except (TypeError, ValueError):
                continue
            if slot.get('date') in valid_dates and h >= night_start.get(slot.get('date'), 99):
                has_night = True
                break
        if not has_night:
            return jsonify({'ok': False, 'error': _t('err.night_needs_availability')}), 400

    # Can't request more flight hours than the number of available slots painted
    # (each slot is one hour). 2 squares marked => at most 2h can be requested.
    avail_slots = set()
    for slot in data.get('slots', []):
        try:
            h = int(slot.get('hour'))
        except (TypeError, ValueError):
            continue
        if slot.get('date') in valid_dates and 0 <= h <= 23:
            avail_slots.add((slot.get('date'), h))
    total_req = sum(_num(r.get('hours')) for r in data.get('requests', [])
                    if r.get('hour_type') in HOUR_TYPES and _num(r.get('hours')) > 0)
    if total_req > len(avail_slots) + 1e-6:
        return jsonify({'ok': False, 'error': _t('err.hours_exceed_avail').format(
            requested=f'{total_req:g}', available=len(avail_slots))}), 400

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


def _booking_hours(b):
    """Hours (ints) a booking occupies, e.g. 23:00-24:00 -> [23]."""
    end_h = b.end_time.hour + (24 if b.end_time.date() > b.start_time.date() else 0)
    return list(range(b.start_time.hour, end_h))


def _gather_auto_inputs(iso_year, iso_week, clear_existing):
    """Build the inputs the optimiser needs for a week."""
    days = weekutils.week_dates(iso_year, iso_week)
    week_start = datetime.combine(days[0], datetime.min.time())
    week_end = datetime.combine(days[6] + timedelta(days=1), datetime.min.time())
    hours = list(range(weekutils.GRID_START_HOUR, weekutils.GRID_END_HOUR))

    week_bookings = Booking.query.filter(
        Booking.status != 'cancelled',
        Booking.start_time >= week_start, Booking.start_time < week_end,
    ).all()

    busy = {'instr': set(), 'plane': set(), 'student': set()}
    assigned_h = {}
    if not clear_existing:
        for b in week_bookings:
            d = b.start_time.date().isoformat()
            for h in _booking_hours(b):
                busy['instr'].add((b.instructor_id, d, h))
                busy['plane'].add((b.aircraft_id, d, h))
                busy['student'].add((b.student_id, d, h))
            assigned_h[b.student_id] = assigned_h.get(b.student_id, 0) + b.duration_hours

    submissions = AvailabilitySubmission.query.filter_by(iso_year=iso_year, iso_week=iso_week).all()
    students, student_types = [], {}
    for sub in submissions:
        requested = sum(r.hours for r in sub.requests)
        need = requested - (assigned_h.get(sub.student_id, 0) if not clear_existing else 0)
        avail = {(s.slot_date.isoformat(), s.hour) for s in sub.slots}
        students.append({'id': sub.student_id, 'avail': avail, 'need': max(0, need)})
        types = []
        for r in sub.requests:
            types += [r.hour_type] * int(r.hours + 1e-9)   # floor to whole hours
        student_types[sub.student_id] = types or ['PPL-A']

    instructors = [i.id for i in User.query.filter_by(role='instructor', is_active=True).all()]
    aircraft = [a.id for a in Aircraft.query.filter_by(is_available=True).all()]
    return students, student_types, instructors, aircraft, busy, hours, week_bookings, (week_start, week_end)


@bp.route('/plan/auto', methods=['POST'])
@login_required
@planner_required
def auto_schedule():
    """Run the optimiser and return a PROPOSED schedule (no commit — preview)."""
    from app import scheduler
    data = request.get_json(silent=True) or {}
    parsed = weekutils.parse_week_key(data.get('week')) or weekutils.next_iso()
    iso_year, iso_week = parsed
    clear_existing = bool(data.get('clear_existing'))
    distribute_planes = data.get('distribute_planes', True)
    distribute_week = data.get('distribute_week', True)
    # Students allowed to have their hours split (the rest prefer contiguous blocks).
    split_ids = {int(i) for i in (data.get('split_students') or []) if str(i).isdigit()}

    students, student_types, instructors, aircraft, busy, hours, _wb, _bounds = \
        _gather_auto_inputs(iso_year, iso_week, clear_existing)

    if not instructors or not aircraft:
        return jsonify({'ok': False, 'error': _t('sched.auto_no_resources')}), 400

    chosen = scheduler.solve(students, instructors, aircraft, busy, hours, split_ids, distribute_week)
    assignment = scheduler.assign_resources(chosen, instructors, aircraft, busy, distribute_planes)
    flights = scheduler.group_flights(assignment, student_types)

    # Honour fractional requested hours (e.g. 3.5h): once a student has all their whole hours,
    # extend their last flight by the remaining 30 min if that slot is free and within availability.
    from collections import defaultdict
    need_exact = {s['id']: s['need'] for s in students}
    avail_sets = {s['id']: s['avail'] for s in students}
    by_stu = defaultdict(list)
    for f in flights:
        by_stu[f['student_id']].append(f)
    def _hour_free(f, hour, flights):
        """No other flight uses this flight's instructor or aircraft during `hour`."""
        return not any(g is not f and g['date'] == f['date']
                       and (g['instructor_id'] == f['instructor_id'] or g['aircraft_id'] == f['aircraft_id'])
                       and int(g['start'][:2]) <= hour < int(g['end'][:2])
                       for g in flights)

    for sid, fl in by_stu.items():
        scheduled = sum(int(f['end'][:2]) - int(f['start'][:2]) for f in fl)
        need = need_exact.get(sid, 0)
        frac = round(need - scheduled, 2)
        if scheduled != int(need + 1e-9) or not (0 < frac < 1):
            continue
        avail = avail_sets.get(sid, set())
        mins = int(round(frac * 60))
        # Try to add the remaining fraction at the end of a flight, else at the start of one,
        # staying inside the student's availability and not clashing on instructor/aircraft.
        extended = False
        for f in sorted(fl, key=lambda f: (f['date'], f['end']), reverse=True):
            end_h = int(f['end'][:2])
            if (f['date'], end_h) in avail and _hour_free(f, end_h, flights):
                f['end'] = f"{end_h:02d}:{mins:02d}"
                extended = True
                break
        if extended:
            continue
        for f in sorted(fl, key=lambda f: (f['date'], f['start'])):
            sh = int(f['start'][:2])
            if (f['date'], sh - 1) in avail and _hour_free(f, sh - 1, flights):
                f['start'] = f"{sh - 1:02d}:{60 - mins:02d}"
                break

    def _fhours(f):
        sh, sm = int(f['start'][:2]), int(f['start'][3:5])
        eh, em = int(f['end'][:2]), int(f['end'][3:5])
        return round((eh * 60 + em - (sh * 60 + sm)) / 60.0, 1)

    # Enrich for display
    sname = {u.id: u.full_name for u in User.query.filter(User.id.in_([s['id'] for s in students])).all()} if students else {}
    iname = {u.id: u.full_name for u in User.query.filter_by(role='instructor').all()}
    areg = {a.id: a.registration for a in Aircraft.query.all()}
    for f in flights:
        f['student'] = sname.get(f['student_id'], '')
        f['instructor'] = iname.get(f['instructor_id'], '')
        f['aircraft'] = areg.get(f['aircraft_id'], '')
        f['hours'] = _fhours(f)

    # Per-student summary
    proposed_h = {}
    for f in flights:
        proposed_h[f['student_id']] = proposed_h.get(f['student_id'], 0) + f['hours']
    summary = []
    subs = {sub.student_id: sub for sub in AvailabilitySubmission.query.filter_by(iso_year=iso_year, iso_week=iso_week).all()}
    for s in students:
        sub = subs.get(s['id'])
        req = round(sum(r.hours for r in sub.requests), 1) if sub else 0
        summary.append({'name': sname.get(s['id'], ''), 'requested': req,
                        'proposed': proposed_h.get(s['id'], 0)})
    summary.sort(key=lambda r: r['name'])

    return jsonify({'ok': True, 'flights': flights, 'summary': summary,
                    'clear_existing': clear_existing})


@bp.route('/plan/auto/apply', methods=['POST'])
@login_required
@planner_required
def auto_apply():
    """Commit a previously previewed proposal as bookings."""
    data = request.get_json(silent=True) or {}
    flights = data.get('flights') or []
    clear_existing = bool(data.get('clear_existing'))
    parsed = weekutils.parse_week_key(data.get('week')) or weekutils.next_iso()
    iso_year, iso_week = parsed
    days = weekutils.week_dates(iso_year, iso_week)
    week_start = datetime.combine(days[0], datetime.min.time())
    week_end = datetime.combine(days[6] + timedelta(days=1), datetime.min.time())

    if clear_existing:
        Booking.query.filter(Booking.status != 'cancelled',
                             Booking.start_time >= week_start,
                             Booking.start_time < week_end).delete(synchronize_session=False)
        db.session.flush()

    created, skipped = 0, 0
    for f in flights:
        try:
            slot_date = date.fromisoformat(f['date'])
            sh, sm = int(f['start'][:2]), int(f['start'][3:5])
            eh, em = int(f['end'][:2]), int(f['end'][3:5])
            start_time = datetime.combine(slot_date, datetime.min.time()).replace(hour=sh, minute=sm)
            end_time = (datetime.combine(slot_date, datetime.min.time()) + timedelta(days=1)) if eh == 24 \
                else datetime.combine(slot_date, datetime.min.time()).replace(hour=eh, minute=em)
            student_id = int(f['student_id']); instructor_id = int(f['instructor_id'])
            aircraft_id = int(f['aircraft_id'])
            hour_type = f['hour_type'] if f.get('hour_type') in HOUR_TYPES else 'PPL-A'
        except (KeyError, ValueError, TypeError):
            skipped += 1
            continue
        if Booking.has_conflict(aircraft_id, instructor_id, student_id, start_time, end_time):
            skipped += 1
            continue
        db.session.add(Booking(student_id=student_id, instructor_id=instructor_id, aircraft_id=aircraft_id,
                               start_time=start_time, end_time=end_time, hour_type=hour_type,
                               flight_type='training', status='confirmed', notes=''))
        created += 1
    db.session.commit()
    return jsonify({'ok': True, 'created': created, 'skipped': skipped})


@bp.route('/plan/reset', methods=['POST'])
@login_required
@planner_required
def reset_plan():
    """Delete all bookings for the given week (reset the planning board)."""
    data = request.get_json(silent=True) or {}
    parsed = weekutils.parse_week_key(data.get('week')) or weekutils.next_iso()
    iso_year, iso_week = parsed
    days = weekutils.week_dates(iso_year, iso_week)
    week_start = datetime.combine(days[0], datetime.min.time())
    week_end = datetime.combine(days[6] + timedelta(days=1), datetime.min.time())
    n = Booking.query.filter(
        Booking.status != 'cancelled',
        Booking.start_time >= week_start,
        Booking.start_time < week_end,
    ).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'ok': True, 'deleted': n})


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

    # Night flights can't start before sunset at the airfield.
    if hour_type == 'Night':
        from app.sun import sunset_local
        ss = sunset_local(slot_date)
        if ss and start_time < ss:
            return jsonify({'ok': False,
                            'error': _t('err.night_before_sunset').format(sunset=ss.strftime('%H:%M'))}), 400

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
