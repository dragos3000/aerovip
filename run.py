from app import create_app, db
from app.models import User, Aircraft

app = create_app()


def _seed_week_availability(iso_year, iso_week):
    """(Re)seed sample student availability for one ISO week, honouring ALL the
    scheduling rules: only operating days, only operating hours (daytime) OR
    after-sunset (Night) cells, requested hours <= painted slots, PPL-A stands
    alone, and any Night request has an after-sunset slot.

    Slots are GENERATED from each day's real operating window + sunset, so the
    sample data stays valid whatever the configured hours/days are."""
    from app import weekutils, operating
    from app.sun import sunset_local
    from app.models import AvailabilitySubmission, AvailabilitySlot, FlightRequest
    from datetime import date as _date
    from math import ceil

    open_days = weekutils.open_week_dates(iso_year, iso_week)
    if not open_days:
        return 0

    # Per-open-day: local operating window [lo, hi) and night-start hour (sunset).
    win = {}
    for d in open_days:
        iso = d.isoformat()
        lo, hi = operating.operating_hours_local(d)
        lo = max(0, lo); hi = min(weekutils.GRID_END_HOUR, hi)
        ss = sunset_local(d)
        night = (ss.hour + (1 if ss.minute else 0)) if ss else 99
        win[iso] = {'day': list(range(lo, hi)),
                    'night': list(range(min(night, weekutils.GRID_END_HOUR), weekutils.GRID_END_HOUR))}

    # Abstract profiles: which open day + the requested hours. Night hours are
    # painted in the after-sunset window and every other type in the daytime
    # operating window — a mixed student gets availability in BOTH windows.
    profiles = [
        {'day': 0, 'req': [('PPL-A', 3.0)]},
        {'day': 1, 'req': [('Buildup', 2.0), ('AUPRT', 1.0)]},
        {'day': 2, 'req': [('Night', 1.5), ('Buildup', 1.0)]},
        {'day': 3, 'req': [('PPL-A', 2.0)]},
        {'day': 4, 'req': [('AUPRT', 2.0)]},
        {'day': 0, 'req': [('Night', 1.0), ('AUPRT', 1.5)]},
        {'day': 1, 'req': [('PPL-A', 4.0)]},
        {'day': 2, 'req': [('Buildup', 3.0)]},
        {'day': 3, 'req': [('PPL-A', 1.5)]},
        {'day': 4, 'req': [('Night', 2.0)]},
        {'day': 0, 'req': [('Buildup', 1.0), ('Night', 1.0)]},
        {'day': 1, 'req': [('PPL-A', 2.5)]},
    ]

    def _clamp_reqs(reqs, capacity):
        """Trim requested hours so their sum fits the painted-slot capacity."""
        out, budget = [], capacity
        for t, h in reqs:
            take = min(h, budget)
            if take > 1e-9:
                out.append((t, round(take, 1)))
                budget -= take
        return out

    students = User.query.filter_by(role='student').order_by(User.first_name).all()
    if not students:
        print('No students found — run `flask seed` first.')
        return 0

    seeded = 0
    for i, stu in enumerate(students):
        p = profiles[i % len(profiles)]
        day = open_days[p['day'] % len(open_days)]
        iso = day.isoformat()
        day_pool = win[iso]['day']
        night_pool = win[iso]['night']

        # Split requests: Night -> night window, everything else -> daytime window.
        night_reqs = [(t, h) for t, h in p['req'] if t == 'Night']
        day_reqs = [(t, h) for t, h in p['req'] if t != 'Night']

        # Day-type availability: a generous, staggered block inside the operating
        # window, so students don't all pile onto the opening hour (which starves
        # the scheduler — capacity is min(free instructors, free aircraft) per
        # hour). Night hours get the whole after-sunset window.
        day_need = ceil(sum(h for _t, h in day_reqs) - 1e-9)
        day_hours = []
        if day_reqs and day_pool:
            block = min(len(day_pool), max(day_need + 3, 5))
            span = max(1, len(day_pool) - block + 1)
            off = (i * 2) % span                      # stagger the start per student
            day_hours = day_pool[off:off + block]

        night_hours = night_pool[:] if (night_reqs and night_pool) else []

        # Clamp each group to what its own window can hold; drop Night if there's
        # no night window that day.
        day_reqs = _clamp_reqs(day_reqs, len(day_hours))
        night_reqs = _clamp_reqs(night_reqs, len(night_hours)) if night_hours else []

        # Combine slots, de-duplicating in case the windows overlap (e.g. winter).
        hours = []
        for h in day_hours + night_hours:
            if h not in hours:
                hours.append(h)
        slots = [(iso, h) for h in hours]
        reqs = day_reqs + night_reqs
        # Final safety: requested total must never exceed painted slots.
        if sum(h for _t, h in reqs) > len(slots):
            reqs = _clamp_reqs(reqs, len(slots))
        if not reqs or not slots:
            continue

        sub = AvailabilitySubmission.query.filter_by(
            student_id=stu.id, iso_year=iso_year, iso_week=iso_week).first()
        if sub:
            AvailabilitySlot.query.filter_by(submission_id=sub.id).delete()
            FlightRequest.query.filter_by(submission_id=sub.id).delete()
        else:
            sub = AvailabilitySubmission(student_id=stu.id, iso_year=iso_year, iso_week=iso_week)
            db.session.add(sub)
            db.session.flush()
        sub.notes = 'Sample availability'
        for d_iso, h in slots:
            db.session.add(AvailabilitySlot(submission_id=sub.id, slot_date=_date.fromisoformat(d_iso), hour=h))
        for t, h in reqs:
            db.session.add(FlightRequest(submission_id=sub.id, hour_type=t, hours=h))
        seeded += 1

    db.session.commit()
    return seeded


def _delete_closed_day_bookings(iso_year, iso_week):
    """Delete bookings that fall on closed (non-operating) weekdays for one ISO week."""
    from app import weekutils, operating
    from app.models import Booking
    from datetime import datetime as _dt, timedelta as _td

    days = weekutils.week_dates(iso_year, iso_week)
    week_start = _dt.combine(days[0], _dt.min.time())
    week_end = _dt.combine(days[6] + _td(days=1), _dt.min.time())
    closed = operating.closed_weekdays()
    deleted = 0
    for b in Booking.query.filter(Booking.start_time >= week_start,
                                  Booking.start_time < week_end).all():
        if b.start_time.weekday() in closed:
            db.session.delete(b)
            deleted += 1
    db.session.commit()
    return deleted


@app.cli.command('seed-availability')
def seed_availability():
    """(Re)seed sample student availability for the upcoming week."""
    from app import weekutils
    iso_year, iso_week = weekutils.next_iso()
    seeded = _seed_week_availability(iso_year, iso_week)
    print(f'Re-seeded availability for {seeded} students, week {iso_year}-W{iso_week:02d}.')


@app.cli.command('reseed-current-next')
def reseed_current_next():
    """Drop bookings on closed days (e.g. Saturday) and reseed sample availability,
    for both the current and next ISO week, honouring the configured operating days."""
    from app import weekutils
    weeks = [weekutils.current_iso(), weekutils.next_iso()]
    for iso_year, iso_week in weeks:
        removed = _delete_closed_day_bookings(iso_year, iso_week)
        seeded = _seed_week_availability(iso_year, iso_week)
        print(f'Week {iso_year}-W{iso_week:02d}: deleted {removed} closed-day booking(s), '
              f're-seeded availability for {seeded} student(s).')


@app.cli.command('gen-vapid')
def gen_vapid():
    """Generate a Web Push VAPID key pair and store it in Settings."""
    from py_vapid import Vapid01
    from cryptography.hazmat.primitives import serialization
    import base64
    from app.models import Setting
    v = Vapid01()
    v.generate_keys()
    priv_pem = v.private_pem().decode()
    raw = v.public_key.public_bytes(serialization.Encoding.X962,
                                    serialization.PublicFormat.UncompressedPoint)
    app_key = base64.urlsafe_b64encode(raw).rstrip(b'=').decode()
    Setting.set('vapid_private', priv_pem, 'Web Push VAPID private key (PEM)')
    Setting.set('vapid_public', app_key, 'Web Push VAPID public key (applicationServerKey)')
    if not Setting.get('vapid_contact', ''):
        Setting.set('vapid_contact', 'mailto:admin@aerovip.ro', 'Web Push contact')
    print('VAPID keys generated and stored in Settings.')
    print('Public key:', app_key)


@app.cli.command('seed')
def seed():
    """Create initial admin user and sample data."""
    db.create_all()

    if not User.query.filter_by(email='admin@aerovip.ro').first():
        admin = User(
            email='admin@aerovip.ro',
            first_name='Admin',
            last_name='Aero Vip',
            role='admin',
            is_active=True,
        )
        admin.set_password('admin123')
        db.session.add(admin)

    if not User.query.filter_by(email='instructor@aerovip.ro').first():
        instructor = User(
            email='instructor@aerovip.ro',
            first_name='Ion',
            last_name='Popescu',
            role='instructor',
            phone='+40 722 000 001',
            is_active=True,
        )
        instructor.set_password('instructor123')
        db.session.add(instructor)

    if not User.query.filter_by(email='student@aerovip.ro').first():
        student = User(
            email='student@aerovip.ro',
            first_name='Maria',
            last_name='Ionescu',
            role='student',
            phone='+40 722 000 002',
            is_active=True,
        )
        student.set_password('student123')
        db.session.add(student)

    if not Aircraft.query.filter_by(registration='YR-AVP').first():
        db.session.add(Aircraft(
            registration='YR-AVP',
            aircraft_type='SEP',
            model='Cessna 172S',
            seats=4,
            hourly_rate=180.00,
            is_available=True,
        ))

    if not Aircraft.query.filter_by(registration='YR-AVR').first():
        db.session.add(Aircraft(
            registration='YR-AVR',
            aircraft_type='SEP',
            model='Piper PA-28',
            seats=4,
            hourly_rate=160.00,
            is_available=True,
        ))

    if not Aircraft.query.filter_by(registration='YR-AVS').first():
        db.session.add(Aircraft(
            registration='YR-AVS',
            aircraft_type='MEP',
            model='Piper PA-34 Seneca',
            seats=6,
            hourly_rate=350.00,
            is_available=True,
        ))

    db.session.commit()
    print('Seed data created successfully!')
    print('Admin: admin@aerovip.ro / admin123')
    print('Instructor: instructor@aerovip.ro / instructor123')
    print('Student: student@aerovip.ro / student123')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
