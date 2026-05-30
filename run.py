from app import create_app, db
from app.models import User, Aircraft

app = create_app()


@app.cli.command('seed-availability')
def seed_availability():
    """(Re)seed sample student availability for the upcoming week, honouring the
    scheduling rules: requested hours <= painted slots, PPL-A can't be mixed with
    other types, and Night hours require availability after sunset."""
    from app import weekutils
    from app.sun import sunset_local
    from app.models import AvailabilitySubmission, AvailabilitySlot, FlightRequest
    from datetime import date as _date

    iso_year, iso_week = weekutils.next_iso()
    days = weekutils.week_dates(iso_year, iso_week)          # Mon..Sun
    night_start = {}
    for d in days:
        ss = sunset_local(d)
        night_start[d.isoformat()] = (ss.hour + (1 if ss.minute else 0)) if ss else 99

    # Each profile: list of (day_index, hour) slots + list of (hour_type, hours).
    # All are built so that sum(hours) <= len(slots), PPL-A stands alone, and any
    # Night request has at least one slot at/after that day's night-start hour.
    profiles = [
        {'slots': [(0, h) for h in (10, 11, 12, 13)], 'req': [('PPL-A', 3.0)]},
        {'slots': [(1, h) for h in (9, 10, 11, 12)],   'req': [('Buildup', 2.0), ('AUPRT', 1.0)]},
        {'slots': [(2, h) for h in (19, 20, 21, 22)],  'req': [('Night', 1.5), ('Buildup', 1.0)]},
        {'slots': [(3, h) for h in (14, 15)],          'req': [('PPL-A', 2.0)]},
        {'slots': [(4, h) for h in (8, 9, 10)],        'req': [('AUPRT', 2.0)]},
        {'slots': [(0, h) for h in (20, 21, 22, 23)],  'req': [('Night', 1.0), ('AUPRT', 1.5)]},
        {'slots': [(1, h) for h in (9, 10, 11, 12, 13)], 'req': [('PPL-A', 4.0)]},
        {'slots': [(2, h) for h in (10, 11, 12, 13)],  'req': [('Buildup', 3.0)]},
        {'slots': [(3, h) for h in (16, 17)],          'req': [('PPL-A', 1.5)]},
        {'slots': [(4, h) for h in (21, 22, 23)],      'req': [('Night', 2.0)]},
        {'slots': [(5, h) for h in (19, 20, 21, 22)],  'req': [('Buildup', 2.0), ('Night', 1.0)]},
        {'slots': [(6, h) for h in (9, 10, 11)],       'req': [('PPL-A', 2.5)]},
    ]

    students = User.query.filter_by(role='student').order_by(User.first_name).all()
    if not students:
        print('No students found — run `flask seed` first.')
        return

    seeded = 0
    for i, stu in enumerate(students):
        p = profiles[i % len(profiles)]
        slots = [(days[di].isoformat(), h) for (di, h) in p['slots']]
        total_req = sum(h for _t, h in p['req'])

        # Safety checks so we never seed data that breaks the app's own rules.
        assert total_req <= len(slots) + 1e-6, (stu.full_name, total_req, len(slots))
        types = {t for t, _h in p['req']}
        assert not ('PPL-A' in types and types - {'PPL-A'}), stu.full_name
        if 'Night' in types:
            assert any(h >= night_start[d] for (d, h) in slots), stu.full_name

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
        for d, h in slots:
            db.session.add(AvailabilitySlot(submission_id=sub.id, slot_date=_date.fromisoformat(d), hour=h))
        for t, h in p['req']:
            db.session.add(FlightRequest(submission_id=sub.id, hour_type=t, hours=round(h, 1)))
        seeded += 1

    db.session.commit()
    print(f'Re-seeded availability for {seeded} students, week {iso_year}-W{iso_week:02d}.')


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
