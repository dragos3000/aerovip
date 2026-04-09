from flask import Blueprint, render_template, jsonify, current_app, session, redirect, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import requests
from app.models import Booking, User, Aircraft, Setting
from app.weather_cache import get_cached_weather, get_cached_notams

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/lang/<lang>')
def set_language(lang):
    if lang in ('en', 'ro'):
        session['lang'] = lang
    return redirect(request.referrer or '/')


@bp.route('/dashboard')
@login_required
def dashboard():
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)

    if current_user.role == 'student':
        my_bookings = Booking.query.filter(
            Booking.student_id == current_user.id,
            Booking.status != 'cancelled',
            Booking.start_time >= today,
        ).order_by(Booking.start_time).limit(10).all()
    elif current_user.role == 'instructor':
        my_bookings = Booking.query.filter(
            Booking.instructor_id == current_user.id,
            Booking.status != 'cancelled',
            Booking.start_time >= today,
        ).order_by(Booking.start_time).limit(10).all()
    else:
        my_bookings = Booking.query.filter(
            Booking.status != 'cancelled',
            Booking.start_time >= today,
        ).order_by(Booking.start_time).limit(20).all()

    todays_flights = Booking.query.filter(
        Booking.start_time >= today,
        Booking.start_time < tomorrow,
        Booking.status != 'cancelled',
    ).count()

    total_students = User.query.filter_by(role='student', is_active=True).count()
    total_aircraft = Aircraft.query.filter_by(is_available=True).count()
    total_instructors = User.query.filter_by(role='instructor', is_active=True).count()

    icao = Setting.get('icao_airport', '') or current_app.config.get('ICAO_AIRPORT', 'LRBS')

    return render_template('dashboard.html',
                           bookings=my_bookings,
                           todays_flights=todays_flights,
                           total_students=total_students,
                           total_aircraft=total_aircraft,
                           total_instructors=total_instructors,
                           icao_airport=icao)


@bp.route('/api/airfield-weather')
@login_required
def airfield_weather():
    """Fetch live weather from the local Ecowitt station (lightweight, no rate limit risk)."""
    airfield_url = Setting.get('airfield_weather_url', '')
    if not airfield_url:
        return jsonify({'error': 'Airfield weather URL not configured. Set it in Admin > Settings.'})

    try:
        resp = requests.get(airfield_url, timeout=8, headers={'User-Agent': 'AeroVip/1.0'})
        resp.raise_for_status()
        data = resp.json()
        return jsonify({'data': data, 'error': None})
    except requests.exceptions.Timeout:
        return jsonify({'error': 'Airfield weather station timed out.'})
    except requests.RequestException:
        return jsonify({'error': 'Failed to fetch airfield weather.'})
    except ValueError:
        return jsonify({'error': 'Invalid response from weather station.'})


@bp.route('/api/weather')
@login_required
def weather():
    """Serve METAR/TAF from background cache (refreshed hourly)."""
    return jsonify(get_cached_weather())


@bp.route('/api/notams')
@login_required
def notams():
    """Serve NOTAMs from background cache (refreshed hourly)."""
    return jsonify(get_cached_notams())
