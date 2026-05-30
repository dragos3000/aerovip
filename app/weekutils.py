"""Helpers for working with ISO weeks (Mon-Sun) used by the scheduling feature."""
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo('Europe/Bucharest')
except Exception:  # pragma: no cover - zoneinfo always present on 3.9+
    LOCAL_TZ = None


def to_utc(dt):
    """Booking times are stored as local wall-clock; convert to UTC for display."""
    if LOCAL_TZ is None or dt is None:
        return dt
    return dt.replace(tzinfo=LOCAL_TZ).astimezone(timezone.utc)


def utc_shift_hours(ref_date):
    """Whole hours to ADD to local time to show UTC for that date (e.g. -3 in summer, -2 winter)."""
    if LOCAL_TZ is None:
        return 0
    aware = datetime.combine(ref_date, datetime.min.time()).replace(hour=12, tzinfo=LOCAL_TZ)
    off = aware.utcoffset()
    return -int(off.total_seconds() // 3600)

DAY_NAMES_EN = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

# Hour range shown on the availability grid / planning board (start hours).
GRID_START_HOUR = 6
GRID_END_HOUR = 22  # exclusive: last selectable cell starts at 21:00


def current_iso(today=None):
    """Return (iso_year, iso_week) for today (or a given date)."""
    today = today or datetime.utcnow().date()
    iso = today.isocalendar()
    return iso[0], iso[1]


def shift_week(iso_year, iso_week, delta):
    """Return (iso_year, iso_week) shifted by `delta` weeks."""
    monday = date.fromisocalendar(iso_year, iso_week, 1)
    monday += timedelta(weeks=delta)
    iso = monday.isocalendar()
    return iso[0], iso[1]


def next_iso(today=None):
    """The ISO (year, week) of next week."""
    y, w = current_iso(today)
    return shift_week(y, w, 1)


def week_dates(iso_year, iso_week):
    """List of 7 date objects, Monday..Sunday, for the given ISO week."""
    monday = date.fromisocalendar(iso_year, iso_week, 1)
    return [monday + timedelta(days=i) for i in range(7)]


def week_range_label(iso_year, iso_week):
    """e.g. 'Jun 1 – Jun 7, 2026'."""
    days = week_dates(iso_year, iso_week)
    start, end = days[0], days[6]
    if start.month == end.month:
        return f"{start.strftime('%b %-d')}–{end.strftime('%-d')}, {end.year}"
    return f"{start.strftime('%b %-d')} – {end.strftime('%b %-d')}, {end.year}"


def week_key(iso_year, iso_week):
    """Canonical string key like '2026-W23'."""
    return f"{iso_year}-W{iso_week:02d}"


def parse_week_key(value):
    """Parse '2026-W23' -> (2026, 23). Returns None if invalid."""
    if not value or 'W' not in value:
        return None
    try:
        y, w = value.split('-W')
        return int(y), int(w)
    except (ValueError, AttributeError):
        return None


def upcoming_weeks(count=5, today=None):
    """List of dicts for the next `count` weeks starting next week (for a selector)."""
    weeks = []
    y, w = next_iso(today)
    for _ in range(count):
        weeks.append({
            'iso_year': y,
            'iso_week': w,
            'key': week_key(y, w),
            'label': week_range_label(y, w),
        })
        y, w = shift_week(y, w, 1)
    return weeks


def week_context(iso_year, iso_week):
    """Bundle commonly needed week info for templates."""
    days = week_dates(iso_year, iso_week)
    return {
        'iso_year': iso_year,
        'iso_week': iso_week,
        'key': week_key(iso_year, iso_week),
        'label': week_range_label(iso_year, iso_week),
        'days': days,
        'day_names': DAY_NAMES_EN,
        'prev_key': week_key(*shift_week(iso_year, iso_week, -1)),
        'next_key': week_key(*shift_week(iso_year, iso_week, 1)),
    }
