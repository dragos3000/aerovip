from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(64), nullable=False)
    last_name = db.Column(db.String(64), nullable=False)
    phone = db.Column(db.String(20))
    role = db.Column(db.String(20), nullable=False, default='student')  # student, instructor, admin
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    student_bookings = db.relationship('Booking', foreign_keys='Booking.student_id', backref='student', lazy='dynamic')
    instructor_bookings = db.relationship('Booking', foreign_keys='Booking.instructor_id', backref='instructor', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __repr__(self):
        return f'<User {self.email}>'


class Aircraft(db.Model):
    __tablename__ = 'aircraft'

    id = db.Column(db.Integer, primary_key=True)
    registration = db.Column(db.String(10), unique=True, nullable=False)
    aircraft_type = db.Column(db.String(64), nullable=False)
    model = db.Column(db.String(64), nullable=False)
    seats = db.Column(db.Integer, default=2)
    hourly_rate = db.Column(db.Numeric(10, 2))
    is_available = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    image_url = db.Column(db.String(256))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bookings = db.relationship('Booking', backref='aircraft', lazy='dynamic')

    def __repr__(self):
        return f'<Aircraft {self.registration}>'


class Booking(db.Model):
    __tablename__ = 'bookings'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    aircraft_id = db.Column(db.Integer, db.ForeignKey('aircraft.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    flight_type = db.Column(db.String(32), nullable=False, default='training')  # training, solo, checkride, intro
    status = db.Column(db.String(20), default='confirmed')  # confirmed, cancelled, completed
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_booking_times', 'start_time', 'end_time'),
    )

    @staticmethod
    def has_conflict(aircraft_id, instructor_id, student_id, start_time, end_time, exclude_id=None):
        """Check for double-booking conflicts on aircraft, instructor, or student."""
        base_query = Booking.query.filter(
            Booking.status != 'cancelled',
            Booking.start_time < end_time,
            Booking.end_time > start_time,
        )
        if exclude_id:
            base_query = base_query.filter(Booking.id != exclude_id)

        # Check aircraft conflict
        if base_query.filter(Booking.aircraft_id == aircraft_id).first():
            return 'Aircraft is already booked for this time slot.'

        # Check instructor conflict
        if base_query.filter(Booking.instructor_id == instructor_id).first():
            return 'Instructor is already booked for this time slot.'

        # Check student conflict
        if base_query.filter(Booking.student_id == student_id).first():
            return 'Student already has a booking for this time slot.'

        return None

    def __repr__(self):
        return f'<Booking {self.id} {self.start_time}>'


class Setting(db.Model):
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=False, default='')
    description = db.Column(db.String(256))

    @staticmethod
    def get(key, default=''):
        setting = Setting.query.filter_by(key=key).first()
        return setting.value if setting else default

    @staticmethod
    def set(key, value, description=None):
        setting = Setting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
            if description:
                setting.description = description
        else:
            setting = Setting(key=key, value=value, description=description or '')
            db.session.add(setting)
        db.session.commit()
        return setting

    def __repr__(self):
        return f'<Setting {self.key}>'
