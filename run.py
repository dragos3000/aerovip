from app import create_app, db
from app.models import User, Aircraft

app = create_app()


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
