"""Airfield operating window — editable in Settings, enforced on availability/planning.

All values are stored as Settings (key/value). Two things are configurable:

  * Operating HOURS — the daytime window students may mark availability in. Stored
    in UTC (the school thinks in UTC); converted to local wall-clock per date for
    the grid, which is DST-aware. After-sunset (Night) cells stay pickable outside
    this window, because night training is flown at a different non-stop airport.
  * Operating DAYS — whether Saturday / Sunday are used. Mon-Fri are always open.

Defaults match the school's current setup: 05:00-15:00 UTC, Monday-Friday only.
"""
from app.models import Setting
from app import weekutils

# Setting keys + their defaults.
OP_START_KEY = 'op_hours_start_utc'
OP_END_KEY = 'op_hours_end_utc'

DEFAULT_START_UTC = 5
DEFAULT_END_UTC = 15   # exclusive

# Per-weekday operating toggles (Mon=0 … Sun=6). Every day is configurable; the
# defaults keep the school's current setup (Mon-Fri open, weekend closed).
DAY_ABBR = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
DAY_SETTING_KEYS = {wd: 'op_day_' + DAY_ABBR[wd] for wd in range(7)}
DEFAULT_DAY_OPEN = {0: True, 1: True, 2: True, 3: True, 4: True, 5: False, 6: False}

# Back-compat aliases (Sat/Sun were the only configurable days originally).
OP_SAT_KEY = DAY_SETTING_KEYS[5]
OP_SUN_KEY = DAY_SETTING_KEYS[6]
DEFAULT_SAT = DEFAULT_DAY_OPEN[5]
DEFAULT_SUN = DEFAULT_DAY_OPEN[6]


def _get_int(key, default):
    try:
        return int(Setting.get(key, str(default)))
    except (TypeError, ValueError):
        return default


def _get_bool(key, default):
    val = Setting.get(key, '1' if default else '0')
    return str(val) in ('1', 'true', 'True', 'on')


def operating_hours_utc():
    """(start, end) operating hours in UTC; end is exclusive."""
    return _get_int(OP_START_KEY, DEFAULT_START_UTC), _get_int(OP_END_KEY, DEFAULT_END_UTC)


def operating_hours_local(ref_date):
    """(start, end) operating hours in local wall-clock for a given date (DST-aware)."""
    start_utc, end_utc = operating_hours_utc()
    shift = weekutils.utc_shift_hours(ref_date)   # local + shift = UTC, so local = UTC - shift
    return start_utc - shift, end_utc - shift


def is_day_open(weekday):
    """Whether the school operates on the given weekday (Mon=0 … Sun=6)."""
    return _get_bool(DAY_SETTING_KEYS[weekday], DEFAULT_DAY_OPEN[weekday])


def is_saturday_open():
    return is_day_open(5)


def is_sunday_open():
    return is_day_open(6)


def open_days_map():
    """{weekday: bool} for all 7 days — used to render the settings toggles."""
    return {wd: is_day_open(wd) for wd in range(7)}


def closed_weekdays():
    """Set of weekday ints the school is closed on (Mon=0 … Sun=6)."""
    try:
        return {wd for wd in range(7) if not is_day_open(wd)}
    except Exception:
        # DB not ready (e.g. before tables exist) — fall back to the defaults.
        return {wd for wd, op in DEFAULT_DAY_OPEN.items() if not op}
