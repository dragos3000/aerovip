"""Background cache for METAR/TAF and NOTAMs.

Fetches data once per hour in a single daemon thread. Results are
stored in a shared JSON file so all gunicorn workers can read the
same cache without each hitting external APIs.
"""
import fcntl
import json
import os
import ssl
import threading
import time
import logging
from datetime import datetime

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 3600  # 1 hour
CACHE_FILE = '/tmp/aerovip_weather_cache.json'
LOCK_FILE = '/tmp/aerovip_weather_refresh.lock'


# ── SSL adapter for ROMATSA ──────────────────────────────────────
class _RomatsaSSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.set_ciphers('DEFAULT:@SECLEVEL=1')
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)


# ── File-based cache read/write ──────────────────────────────────
def _read_cache():
    """Read cache from shared JSON file."""
    try:
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_cache(data):
    """Atomically write cache to shared JSON file."""
    tmp = CACHE_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.replace(tmp, CACHE_FILE)


# ── Fetch functions (run in background thread) ───────────────────
def _fetch_weather(api_key, icao):
    result = {'metar': None, 'taf': None, 'station': icao, 'fallback': False, 'error': None}

    if not api_key or api_key == 'your-checkwx-api-key-here':
        result['error'] = 'Weather API key not configured. Set it in Admin > Settings.'
        return result

    try:
        headers = {'X-API-Key': api_key}

        metar_resp = requests.get(
            f'https://api.checkwx.com/metar/{icao}/decoded',
            headers=headers, timeout=10,
        )
        if metar_resp.ok:
            data = metar_resp.json()
            if data.get('results', 0) > 0:
                result['metar'] = data['data'][0]

        if not result['metar']:
            station_resp = requests.get(
                f'https://api.checkwx.com/station/{icao}',
                headers=headers, timeout=10,
            )
            if station_resp.ok:
                sdata = station_resp.json()
                if sdata.get('results', 0) > 0:
                    coords = sdata['data'][0].get('geometry', {}).get('coordinates', [])
                    if len(coords) >= 2:
                        lon, lat = coords[0], coords[1]
                        nearby_resp = requests.get(
                            f'https://api.checkwx.com/metar/lat/{lat}/lon/{lon}/decoded?radius=100',
                            headers=headers, timeout=10,
                        )
                        if nearby_resp.ok:
                            ndata = nearby_resp.json()
                            if ndata.get('results', 0) > 0:
                                result['metar'] = ndata['data'][0]
                                result['station'] = ndata['data'][0].get('station', {}).get('icao', '?')
                                result['fallback'] = True

        taf_icao = result['station']
        taf_resp = requests.get(
            f'https://api.checkwx.com/taf/{taf_icao}/decoded',
            headers=headers, timeout=10,
        )
        if taf_resp.ok:
            data = taf_resp.json()
            if data.get('results', 0) > 0:
                result['taf'] = data['data'][0]

    except requests.RequestException as e:
        result['error'] = f'Failed to fetch weather: {e}'

    return result


def _fetch_notams(icao):
    result = {'notams': [], 'icao': icao, 'source': 'ROMATSA', 'error': None}

    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        s = requests.Session()
        s.mount('https://', _RomatsaSSLAdapter(max_retries=2))

        resp = s.get(
            f'https://flightplan.romatsa.ro/init/notam/getnotamlist?ad={icao}',
            timeout=(5, 20),
            verify=False,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        tables = soup.find_all('table')
        if len(tables) < 2:
            return result

        for row in tables[1].find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 3:
                continue
            notam_id = cells[0].get_text(strip=True)
            raw_text = cells[2].get_text(strip=True)
            link_tag = cells[0].find('a')
            link = ('https://flightplan.romatsa.ro' + link_tag['href']) if link_tag else ''

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

            result['notams'].append({
                'id': notam_id,
                'raw': raw_text,
                'text': e_text or raw_text,
                'link': link,
            })

    except requests.exceptions.Timeout:
        result['error'] = 'ROMATSA server timed out.'
    except requests.exceptions.ConnectionError:
        result['error'] = 'Could not connect to ROMATSA. Server may be down.'
    except requests.RequestException as e:
        result['error'] = f'ROMATSA error: {e.response.status_code}' if e.response else 'Failed to fetch NOTAMs.'

    return result


# ── Background loop ──────────────────────────────────────────────
def _refresh_loop(app):
    """Runs in a daemon thread. Uses a file lock so only one worker refreshes."""
    while True:
        lock_fd = None
        try:
            # Try to acquire exclusive lock — only one worker refreshes
            lock_fd = open(LOCK_FILE, 'w')
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            with app.app_context():
                from app.models import Setting
                api_key = Setting.get('checkwx_api_key', '') or app.config.get('CHECKWX_API_KEY', '')
                icao = Setting.get('icao_airport', '') or app.config.get('ICAO_AIRPORT', 'LRBS')

            logger.info('Weather cache: refreshing METAR/TAF and NOTAMs for %s', icao)
            weather = _fetch_weather(api_key, icao)
            notams = _fetch_notams(icao)

            now = datetime.utcnow().isoformat() + 'Z'
            _write_cache({
                'weather': weather,
                'notams': notams,
                'cached_at': now,
            })
            logger.info('Weather cache: refresh complete at %s', now)

            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

        except BlockingIOError:
            # Another worker already holds the lock — skip this cycle
            if lock_fd:
                lock_fd.close()
        except Exception:
            logger.exception('Weather cache: refresh failed')
            if lock_fd:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    lock_fd.close()
                except Exception:
                    pass

        time.sleep(REFRESH_SECONDS)


def start_background_refresh(app):
    """Call once at app startup to begin the background refresh thread."""
    t = threading.Thread(target=_refresh_loop, args=(app,), daemon=True)
    t.start()
    logger.info('Weather cache: background thread started (interval=%ds)', REFRESH_SECONDS)


# ── Public getters (called by routes) ────────────────────────────
def get_cached_weather():
    cache = _read_cache()
    if cache and cache.get('weather'):
        result = dict(cache['weather'])
        result['cached_at'] = cache.get('cached_at')
        return result
    return {'metar': None, 'taf': None, 'station': '', 'fallback': False,
            'error': 'Weather data is loading. Please wait a moment and refresh.'}


def get_cached_notams():
    cache = _read_cache()
    if cache and cache.get('notams'):
        result = dict(cache['notams'])
        result['cached_at'] = cache.get('cached_at')
        return result
    return {'notams': [], 'icao': '', 'source': 'ROMATSA',
            'error': 'NOTAMs are loading. Please wait a moment and refresh.'}
