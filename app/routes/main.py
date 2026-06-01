from flask import Blueprint, render_template, jsonify, current_app, session, redirect, request, url_for, send_from_directory
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import requests
from app.models import Booking, User, Aircraft, Setting
from app.weather_cache import get_cached_weather, get_cached_notams
from app.airfield import get_airfield_info, get_airfield_map_url
from app.sun import sun_times

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    # Logged-in users hitting the landing page (e.g. typing /aerovip/) get the app,
    # not the public hero — which would render blank inside the authenticated shell.
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')


@bp.route('/lang/<lang>')
def set_language(lang):
    if lang in ('en', 'ro'):
        session['lang'] = lang
    return redirect(request.referrer or url_for('main.dashboard'))


@bp.route('/tz/<mode>')
def set_tz(mode):
    if mode in ('lt', 'utc'):
        session['tz'] = mode
    return redirect(request.referrer or url_for('main.dashboard'))


@bp.route('/assets/<int:v>/<path:filename>')
def asset(v, filename):
    """Fingerprinted static assets: a new path per file version, so Cloudflare treats
    each change as a brand-new URL (cache miss) instead of serving a stale cached copy."""
    resp = send_from_directory(current_app.static_folder, filename)
    resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return resp


@bp.route('/sw.js')
def service_worker():
    """Serve the PWA service worker at the app root (works under the /aerovip/ prefix)."""
    resp = current_app.send_static_file('sw.js')
    resp.headers['Content-Type'] = 'application/javascript'
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@bp.route('/manifest.webmanifest')
def manifest():
    """Build the PWA manifest with url_for so all paths honor the /aerovip/ prefix."""
    data = {
        'name': 'Aero Vip Academy',
        'short_name': 'Aero Vip',
        'description': 'Flight school scheduling, availability, logbook and airfield info.',
        'start_url': url_for('main.index'),
        'scope': url_for('main.index'),
        'display': 'standalone',
        'background_color': '#0a1628',
        'theme_color': '#0a1628',
        'orientation': 'any',
        'icons': [
            {'src': url_for('static', filename='img/icon-192.png'),
             'sizes': '192x192', 'type': 'image/png', 'purpose': 'any maskable'},
            {'src': url_for('static', filename='img/icon-512.png'),
             'sizes': '512x512', 'type': 'image/png', 'purpose': 'any maskable'},
        ],
    }
    resp = jsonify(data)
    resp.headers['Content-Type'] = 'application/manifest+json'
    return resp


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
        ).order_by(Booking.start_time).limit(200).all()

    # Planners see the upcoming flights split into one table per aircraft.
    flights_by_aircraft = None
    if current_user.is_planner:
        groups = {}
        for b in my_bookings:
            groups.setdefault(b.aircraft_id, []).append(b)
        acs = {a.id: a for a in Aircraft.query.all()}
        flights_by_aircraft = sorted(
            ({'aircraft': acs.get(aid), 'bookings': bks} for aid, bks in groups.items()),
            key=lambda g: g['aircraft'].registration if g['aircraft'] else '~',
        )

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
                           flights_by_aircraft=flights_by_aircraft,
                           todays_flights=todays_flights,
                           total_students=total_students,
                           total_aircraft=total_aircraft,
                           total_instructors=total_instructors,
                           icao_airport=icao,
                           airfield_info=get_airfield_info(),
                           airfield_map_url=get_airfield_map_url(session.get('lang', 'ro')),
                           suntimes=sun_times())


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
