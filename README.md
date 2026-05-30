# Aero Vip Academy — Flight School Scheduling App

A flight school management app (Flask + PostgreSQL) for weekly availability-based
scheduling, an aircraft-centric planning board, an EASA-style pilot logbook,
fleet management, and live airfield/weather information. Installable as a PWA.

## Features

- **Weekly availability scheduling** — students paint their availability on a drag
  grid and request hours by type (PPL-A / Buildup / AUPRT / Night).
- **Aircraft-centric planning board** — one grid per aircraft showing every
  student's availability at once (overlaps in red), drag-to-reschedule, instructor
  double-booking guard, and a per-student requested-hours cap. Mobile shows one day
  at a time via a day selector.
- **EASA pilot logbook** — instructors log flown hours per student/day (total
  auto-calculated from times, shown as H:MM); PPL-A flights get the EASA exercises
  multi-select; filter by student/period; sortable, responsive DataTables.
- **Roles**: Student, Instructor, **Manager**, Admin. Planners (admin + manager)
  build the schedule; instructors log flights and see their assignments.
- **Dashboard**: stats, upcoming flights, live weather, METAR/TAF, NOTAMs, and an
  editable home-airfield info card + embedded map (bilingual).
- **Airfield weather station**: live data from a local Ecowitt station.
- **METAR / TAF**: CheckWX API with nearest-station fallback; cached hourly.
- **NOTAMs**: live from ROMATSA.
- **LT / UTC toggle** across the whole app (incl. weather card times).
- **Bilingual**: Romanian / English.
- **PWA**: installable, with an offline page and a network-first service worker.
- **Mobile-first**: Bootstrap 5 + DataTables Responsive (collapsing tables),
  off-canvas menu.

## Tech Stack

- **Backend**: Python Flask, SQLAlchemy, Flask-Login, Flask-Migrate
- **Database**: PostgreSQL
- **Frontend**: Bootstrap 5, DataTables (Responsive), Bootstrap Icons
- **Deployment**: Gunicorn (port 8086) + Nginx under `start-line.ro/aerovip/`,
  behind Cloudflare, systemd, Let's Encrypt SSL

## Quick Start

```bash
git clone https://github.com/dragos3000/aerovip.git
cd aerovip
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # set DATABASE_URL, SECRET_KEY, CHECKWX_API_KEY, ICAO_AIRPORT

createdb aerovip
flask --app run db upgrade    # NOTE: migrations/ is gitignored — see below
flask --app run seed          # creates default accounts + sample aircraft
python run.py
```

> **Migrations are gitignored** (`.gitignore` → `migrations/`). On a fresh clone
> the migration files aren't present; create the schema with `flask --app run seed`
> (which runs `db.create_all()`) or regenerate migrations with `flask db migrate`.

## Default Accounts

| Role       | Email                  | Password       |
|------------|------------------------|----------------|
| Admin      | admin@aerovip.ro       | admin123       |
| Instructor | instructor@aerovip.ro  | instructor123  |
| Student    | student@aerovip.ro     | student123     |

## Configuration

Managed via **Admin → Settings** in the web UI:

- **CheckWX API key** — free key from [checkwx.com](https://www.checkwx.com) for METAR/TAF/NOTAMs
- **ICAO airport code** — for weather/NOTAMs (e.g. LRPW falls back to nearest station LROP)
- **Airfield weather URL** — JSON endpoint for the local station
- **Home airfield info** — ARP coordinates, elevation, frequencies, airspace, procedures (shown on the dashboard)
- **Airfield map** — Google My Maps embed URL (separate RO / EN maps)

Saving settings triggers an immediate weather-cache refresh.

## Deployment notes

The app is served under a **path prefix** (`/aerovip/`) behind **Cloudflare**.

- Cloudflare caches static assets aggressively and **ignores query strings**, so
  cache-busting uses **fingerprinted asset paths** (`asset_url()` →
  `/aerovip/assets/<mtime>/...`) rather than `?v=`. Changing a static file changes
  its path, so Cloudflare serves it fresh with no manual purge.
- Static files are served by Nginx from `app/static/`; everything else proxies to
  Gunicorn on `127.0.0.1:8086`. `ProxyFix` honours `X-Forwarded-Prefix`.
- The domain is **shared with another Flask app** (`/app/`), so a unique
  `SESSION_COOKIE_NAME = 'aerovip_session'` is set — otherwise both apps' default
  `session` cookies collide and log users out.
- This is a **shared multi-tenant box (96 cores)**, so Gunicorn uses a small fixed
  worker pool (`workers = 3`, `gthread`), NOT `cpu_count()*2+1` (which would spawn
  ~193 workers and eat all the RAM).
- The weather cache refreshes hourly and **skips the API call on restart if the
  cache is still fresh** (avoids burning the CheckWX quota).

```bash
sudo bash deploy.sh
```

## License

MIT
