from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, PasswordField, SelectField, BooleanField, TextAreaField, DecimalField, IntegerField, DateTimeLocalField, DateField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, NumberRange


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')


class DocumentUploadForm(FlaskForm):
    doc_type = SelectField('Document type', choices=[
        ('licence', 'Licence'), ('medical', 'Medical licence'),
        ('id', 'ID'), ('rtf', 'RTF certificate')], validators=[DataRequired()])
    expiry_date = DateField('Expiry date', validators=[DataRequired()])
    file = FileField('File', validators=[
        FileRequired(), FileAllowed(['pdf', 'jpg', 'jpeg', 'png'], 'PDF or image (jpg/png) only.')])
    student_id = SelectField('Student', coerce=int, validators=[Optional()],
                             validate_choice=False)  # shown to planners only; students upload for themselves


class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])


class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])


class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    first_name = StringField('First Name', validators=[DataRequired(), Length(max=64)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(max=64)])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])


class UserEditForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    first_name = StringField('First Name', validators=[DataRequired(), Length(max=64)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(max=64)])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    role = SelectField('Role', choices=[('student', 'Student'), ('instructor', 'Instructor'), ('manager', 'Manager'), ('admin', 'Admin')])
    is_active = BooleanField('Active')


class AircraftForm(FlaskForm):
    registration = StringField('Registration', validators=[DataRequired(), Length(max=10)])
    aircraft_type = StringField('Type (e.g. SEP, MEP)', validators=[DataRequired(), Length(max=64)])
    model = StringField('Model (e.g. Cessna 172)', validators=[DataRequired(), Length(max=64)])
    seats = IntegerField('Seats', validators=[DataRequired(), NumberRange(min=1, max=20)], default=2)
    hourly_rate = DecimalField('Hourly Rate (EUR)', validators=[Optional()], places=2)
    is_available = BooleanField('Available', default=True)
    image_url = StringField('Image URL', validators=[Optional(), Length(max=256)])
    notes = TextAreaField('Notes', validators=[Optional()])


class BookingForm(FlaskForm):
    aircraft_id = SelectField('Aircraft', coerce=int, validators=[DataRequired()])
    instructor_id = SelectField('Instructor', coerce=int, validators=[DataRequired()])
    student_id = SelectField('Student', coerce=int, validators=[DataRequired()])
    start_time = DateTimeLocalField('Start Time', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    end_time = DateTimeLocalField('End Time', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    flight_type = SelectField('Flight Type', choices=[
        ('training', 'Training'),
        ('solo', 'Solo'),
        ('checkride', 'Check Ride'),
        ('intro', 'Introductory Flight'),
    ], validators=[DataRequired()])
    notes = TextAreaField('Notes', validators=[Optional()])


class SettingsForm(FlaskForm):
    checkwx_api_key = StringField('CheckWX API Key', validators=[Optional(), Length(max=256)])
    icao_airport = StringField('ICAO Airport Code', validators=[Optional(), Length(max=10)])
    airfield_weather_url = StringField('Airfield Weather Station URL', validators=[Optional(), Length(max=512)])
    op_hours_start_utc = IntegerField('Operating start (UTC)', validators=[Optional(), NumberRange(min=0, max=23)])
    op_hours_end_utc = IntegerField('Operating end (UTC)', validators=[Optional(), NumberRange(min=1, max=24)])
    op_day_mon = BooleanField('Monday')
    op_day_tue = BooleanField('Tuesday')
    op_day_wed = BooleanField('Wednesday')
    op_day_thu = BooleanField('Thursday')
    op_day_fri = BooleanField('Friday')
    op_day_sat = BooleanField('Saturday')
    op_day_sun = BooleanField('Sunday')
    doc_expiry_warn_days = IntegerField('Document expiry warning (days)', validators=[Optional(), NumberRange(min=1, max=365)])
    # SMTP (admin-only) — for password-reset emails.
    smtp_host = StringField('SMTP host', validators=[Optional(), Length(max=128)])
    smtp_port = IntegerField('SMTP port', validators=[Optional(), NumberRange(min=1, max=65535)])
    smtp_user = StringField('SMTP username', validators=[Optional(), Length(max=128)])
    smtp_pass = PasswordField('SMTP password', validators=[Optional(), Length(max=256)])
    smtp_from = StringField('From address', validators=[Optional(), Length(max=128)])
    smtp_tls = BooleanField('Use STARTTLS')
