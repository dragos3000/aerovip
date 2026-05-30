"""Aeronautical sun times for the home airfield: sunrise, sunset, and civil-twilight
night window. Used on the dashboard and to stop Night flights being scheduled before
sunset. Coordinates come from the airfield ARP setting (parsed from DMS)."""
import re
from datetime import date as date_cls

from astral import LocationInfo
from astral.sun import sun

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo('Europe/Bucharest')
except Exception:  # pragma: no cover
    LOCAL_TZ = None

DEFAULT_LAT, DEFAULT_LON = 44.5711, 26.0858   # LROP fallback


def _parse_coords(s):
    """Parse `DD°MM'SS"N  DDD°MM'SS"E` to (lat, lon) decimal degrees, or None."""
    if not s:
        return None
    matches = re.findall(r"(\d+)\s*°\s*(\d+)\s*'\s*([\d.]+)\s*\"?\s*([NSEW])", s)
    lat = lon = None
    for deg, mn, sec, hemi in matches:
        val = int(deg) + int(mn) / 60.0 + float(sec) / 3600.0
        if hemi in ('S', 'W'):
            val = -val
        if hemi in ('N', 'S'):
            lat = val
        else:
            lon = val
    if lat is None or lon is None:
        return None
    return lat, lon


def airfield_latlon():
    from app.models import Setting
    return _parse_coords(Setting.get('af_arp_coords', '')) or (DEFAULT_LAT, DEFAULT_LON)


def sun_times(on_date=None):
    """Local-naive datetimes for the airfield: dawn, sunrise, sunset, dusk (civil twilight).
    Returns None on failure (e.g. polar day). Times are naive local (Europe/Bucharest)
    so they work with the dashboard's LT/UTC `disp()` helper and the local booking times."""
    try:
        lat, lon = airfield_latlon()
        on_date = on_date or date_cls.today()
        loc = LocationInfo(latitude=lat, longitude=lon)
        s = sun(loc.observer, date=on_date, tzinfo=LOCAL_TZ)
        return {k: s[k].replace(tzinfo=None) for k in ('dawn', 'sunrise', 'sunset', 'dusk')}
    except Exception:
        return None


def sunset_local(on_date):
    """Naive local sunset for the date, or None."""
    s = sun_times(on_date)
    return s['sunset'] if s else None
