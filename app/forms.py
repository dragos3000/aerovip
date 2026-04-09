from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, BooleanField, TextAreaField, DecimalField, IntegerField, DateTimeLocalField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, NumberRange


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')


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
    role = SelectField('Role', choices=[('student', 'Student'), ('instructor', 'Instructor'), ('admin', 'Admin')])
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
