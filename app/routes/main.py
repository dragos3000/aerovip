from flask import Blueprint, render_template, jsonify, current_app, session, redirect, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import ssl
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from bs4 import BeautifulSoup
from app.models import Booking, User, Aircraft, Setting


class _RomatsaSSLAdapter(HTTPAdapter):
    """ROMATSA uses weak DH keys and an incomplete cert chain — relax SSL."""
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.set_ciphers('DEFAULT:@SECLEVEL=1')
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)

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

    _, icao = _get_api_config()

    return render_template('dashboard.html',
                           bookings=my_bookings,
                           todays_flights=todays_flights,
                           total_students=total_students,
                           total_aircraft=total_aircraft,
                           total_instructors=total_instructors,
                           icao_airport=icao)


def _get_api_config():
    """Get CheckWX API key and ICAO from DB settings, falling back to config."""
    api_key = Setting.get('checkwx_api_key', '') or current_app.config.get('CHECKWX_API_KEY', '')
    icao = Setting.get('icao_airport', '') or current_app.config.get('ICAO_AIRPORT', 'LRBS')
    return api_key, icao


@bp.route('/api/airfield-weather')
@login_required
def airfield_weather():
    """Fetch live weather from the LRPW Ecowitt station."""
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
    api_key, icao = _get_api_config()

    result = {'metar': None, 'taf': None, 'station': icao, 'fallback': False, 'error': None}

    if not api_key or api_key == 'your-checkwx-api-key-here':
        result['error'] = 'Weather API key not configured. Set it in Admin > Settings.'
        return jsonify(result)

    try:
        headers = {'X-API-Key': api_key}

        # Try direct METAR for the configured airport
        metar_resp = requests.get(f'https://api.checkwx.com/metar/{icao}/decoded', headers=headers, timeout=5)
        if metar_resp.ok:
            data = metar_resp.json()
            if data.get('results', 0) > 0:
                result['metar'] = data['data'][0]

        # No METAR — find the nearest station via lat/lon
        if not result['metar']:
            station_resp = requests.get(f'https://api.checkwx.com/station/{icao}', headers=headers, timeout=5)
            if station_resp.ok:
                sdata = station_resp.json()
                if sdata.get('results', 0) > 0:
                    coords = sdata['data'][0].get('geometry', {}).get('coordinates', [])
                    if len(coords) >= 2:
                        lon, lat = coords[0], coords[1]
                        nearby_resp = requests.get(
                            f'https://api.checkwx.com/metar/lat/{lat}/lon/{lon}/decoded?radius=100',
                            headers=headers, timeout=5,
                        )
                        if nearby_resp.ok:
                            ndata = nearby_resp.json()
                            if ndata.get('results', 0) > 0:
                                result['metar'] = ndata['data'][0]
                                nearby_icao = ndata['data'][0].get('station', {}).get('icao', '?')
                                result['station'] = nearby_icao
                                result['fallback'] = True

        # TAF — try configured airport first, then fallback station
        taf_icao = result['station']
        taf_resp = requests.get(f'https://api.checkwx.com/taf/{taf_icao}/decoded', headers=headers, timeout=5)
        if taf_resp.ok:
            data = taf_resp.json()
            if data.get('results', 0) > 0:
                result['taf'] = data['data'][0]

    except requests.RequestException:
        result['error'] = 'Failed to fetch weather data.'

    return jsonify(result)


def _fetch_romatsa_notams(icao):
    """Fetch NOTAMs from ROMATSA flightplan portal. Returns list of dicts."""
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    s = requests.Session()
    adapter = _RomatsaSSLAdapter(max_retries=2)
    s.mount('https://', adapter)

    resp = s.get(
        f'https://flightplan.romatsa.ro/init/notam/getnotamlist?ad={icao}',
        timeout=(5, 15),  # 5s connect, 15s read
        verify=False,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'html.parser')
    tables = soup.find_all('table')
    if len(tables) < 2:
        return []

    notams = []
    for row in tables[1].find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 3:
            continue
        notam_id = cells[0].get_text(strip=True)
        raw_text = cells[2].get_text(strip=True)
        link_tag = cells[0].find('a')
        link = ('https://flightplan.romatsa.ro' + link_tag['href']) if link_tag else ''

        # Parse E) field — the human-readable description
        parts = {}
        for field in ('Q)', 'A)', 'B)', 'C)', 'D)', 'E)', 'F)', 'G)'):
            idx = raw_text.find(field)
            if idx != -1:
                parts[field[0]] = idx

        e_text = ''
        if 'E' in parts:
            e_start = parts['E'] + 2
            e_end = parts.get('F', parts.get('G', len(raw_text)))
            e_text = raw_text[e_start:e_end].strip()

        notams.append({
            'id': notam_id,
            'raw': raw_text,
            'text': e_text or raw_text,
            'link': link,
        })
    return notams


@bp.route('/api/notams')
@login_required
def notams():
    _, icao = _get_api_config()

    result = {'notams': [], 'icao': icao, 'source': 'ROMATSA', 'error': None}

    try:
        result['notams'] = _fetch_romatsa_notams(icao)
    except requests.exceptions.Timeout:
        result['error'] = 'ROMATSA server timed out. Try again in a moment.'
    except requests.exceptions.ConnectionError:
        result['error'] = 'Could not connect to ROMATSA. Server may be down.'
    except requests.RequestException as e:
        result['error'] = f'ROMATSA error: {e.response.status_code}' if e.response else 'Failed to fetch NOTAMs from ROMATSA.'

    return jsonify(result)
