from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db

# Types of training hours a student can request / be scheduled for.
HOUR_TYPES = ['PPL-A', 'Buildup', 'AUPRT', 'Night']

# EASA PPL(A) flight training syllabus exercises (FCL) — selectable when logging PPL-A flights.
PPL_EXERCISES = [
    ('1', 'Familiarisation with the aeroplane'),
    ('2', 'Preparation for and action after flight'),
    ('3', 'Air experience'),
    ('4', 'Effects of controls'),
    ('5', 'Taxiing'),
    ('6', 'Straight and level flight'),
    ('7', 'Climbing'),
    ('8', 'Descending'),
    ('9', 'Turning'),
    ('10a', 'Slow flight'),
    ('10b', 'Stalling'),
    ('11', 'Spin avoidance'),
    ('12', 'Take-off and climb to downwind'),
    ('13', 'Circuit, approach and landing'),
    ('14', 'First solo'),
    ('15', 'Advanced turning'),
    ('16', 'Forced landing without power'),
    ('17', 'Precautionary landing'),
    ('18a', 'Navigation'),
    ('18b', 'Navigation at lower levels and reduced visibility'),
    ('18c', 'Radio navigation'),
    ('19', 'Basic instrument flight'),
]
PPL_EXERCISE_LABELS = {code: label for code, label in PPL_EXERCISES}

# Roles allowed to build the weekly schedule (see availability, assign flights).
PLANNER_ROLES = ('admin', 'manager')


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(64), nullable=False)
    last_name = db.Column(db.String(64), nullable=False)
    phone = db.Column(db.String(20))
    role = db.Column(db.String(20), nullable=False, default='student')  # student, instructor, manager, admin
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    student_bookings = db.relationship('Booking', foreign_keys='Booking.student_id', backref='student', lazy='dynamic')
    instructor_bookings = db.relationship('Booking', foreign_keys='Booking.instructor_id', backref='instructor', lazy='dynamic')
    availability_submissions = db.relationship('AvailabilitySubmission', backref='student', lazy='dynamic',
                                               cascade='all, delete-orphan')

    @property
    def is_planner(self):
        """Admins and managers build the weekly schedule."""
        return self.role in PLANNER_ROLES

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
    flight_type = db.Column(db.String(32), nullable=False, default='training')  # legacy: training, solo, checkride, intro
    hour_type = db.Column(db.String(16), nullable=False, default='PPL-A')  # PPL-A, Buildup, AUPRT, Night
    status = db.Column(db.String(20), default='confirmed')  # confirmed, cancelled, completed
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def duration_hours(self):
        return (self.end_time - self.start_time).total_seconds() / 3600.0

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

        # Returns a translation key (resolved by the caller) or None.
        if base_query.filter(Booking.aircraft_id == aircraft_id).first():
            return 'err.aircraft_booked'
        if base_query.filter(Booking.instructor_id == instructor_id).first():
            return 'err.instructor_booked'
        if base_query.filter(Booking.student_id == student_id).first():
            return 'err.student_booked'
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


class AvailabilitySubmission(db.Model):
    """A student's availability for one ISO week (Mon-Sun)."""
    __tablename__ = 'availability_submissions'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    iso_year = db.Column(db.Integer, nullable=False)
    iso_week = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    slots = db.relationship('AvailabilitySlot', backref='submission', lazy='select',
                            cascade='all, delete-orphan')
    requests = db.relationship('FlightRequest', backref='submission', lazy='select',
                               cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('student_id', 'iso_year', 'iso_week', name='uq_availability_student_week'),
    )

    @property
    def total_requested_hours(self):
        return sum(r.hours for r in self.requests)

    def __repr__(self):
        return f'<AvailabilitySubmission s{self.student_id} {self.iso_year}-W{self.iso_week}>'


class AvailabilitySlot(db.Model):
    """One painted hour cell of availability (a single date + hour)."""
    __tablename__ = 'availability_slots'

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('availability_submissions.id'), nullable=False, index=True)
    slot_date = db.Column(db.Date, nullable=False)
    hour = db.Column(db.Integer, nullable=False)  # 0-23, start of the one-hour cell

    __table_args__ = (
        db.UniqueConstraint('submission_id', 'slot_date', 'hour', name='uq_slot_submission_date_hour'),
    )

    def __repr__(self):
        return f'<AvailabilitySlot {self.slot_date} {self.hour}:00>'


class FlightRequest(db.Model):
    """Desired hours of a given type within a week's availability submission."""
    __tablename__ = 'flight_requests'

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('availability_submissions.id'), nullable=False, index=True)
    hour_type = db.Column(db.String(16), nullable=False, default='PPL-A')
    hours = db.Column(db.Float, nullable=False, default=1.0)

    def __repr__(self):
        return f'<FlightRequest {self.hours}h {self.hour_type}>'


class LogbookEntry(db.Model):
    """A student flight log entry (EASA pilot logbook style), filled in by the instructor."""
    __tablename__ = 'logbook_entries'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    aircraft_id = db.Column(db.Integer, db.ForeignKey('aircraft.id'))
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'))

    flight_date = db.Column(db.Date, nullable=False, index=True)
    dep_place = db.Column(db.String(8))      # departure aerodrome (ICAO)
    dep_time = db.Column(db.String(5))       # 'HH:MM' UTC
    arr_place = db.Column(db.String(8))
    arr_time = db.Column(db.String(5))

    hour_type = db.Column(db.String(16), nullable=False, default='PPL-A')
    total_time = db.Column(db.Float, nullable=False, default=0.0)   # total time of flight (h)
    dual_time = db.Column(db.Float, default=0.0)                    # dual instruction received
    pic_time = db.Column(db.Float, default=0.0)                     # pilot-in-command
    landings_day = db.Column(db.Integer, default=0)
    landings_night = db.Column(db.Integer, default=0)

    exercises = db.Column(db.Text)   # comma-separated PPL exercise codes (PPL-A only)
    remarks = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship('User', foreign_keys=[student_id])
    instructor = db.relationship('User', foreign_keys=[instructor_id])
    aircraft = db.relationship('Aircraft')

    @property
    def exercise_codes(self):
        return [c for c in (self.exercises or '').split(',') if c]

    def __repr__(self):
        return f'<LogbookEntry {self.flight_date} s{self.student_id} {self.total_time}h>'
