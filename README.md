# Aero Vip Academy — Flight School Scheduling App

A flight school management app (Flask + PostgreSQL) for weekly availability-based
scheduling, an aircraft-centric planning board, an EASA-style pilot logbook,
fleet management, and live airfield/weather information. Installable as a PWA.

## Features

- **Weekly availability scheduling** — students paint their availability on a drag
  grid and request hours by type (PPL-A / Buildup / AUPRT / Night). Submissions are
  validated against the school's rules:
  - **Requested hours ≤ painted slots** (each square is one hour) — you can't ask
    for 3h while marking only 2 squares.
  - **PPL-A is exclusive** — unlicensed PPL-A training can't be combined with
    Buildup / AUPRT / Night in the same week.
  - **Night needs post-sunset availability** — Night hours require at least one
    marked slot at/after the airfield's sunset (the grid shades the night window).
  - **Operating hours** — daytime slots must fall inside the airfield's configured
    operating window (set in UTC); cells outside it are closed/non-pickable. The
    exception is **after-sunset (Night) cells**, which stay selectable because night
    training is flown at a non-stop airport elsewhere.
  - **Operating days** — only the configured operating weekdays are pickable; unused
    days are removed from both the availability grid and the planning board.
  - **Busy-hour heat** — each hour cell carries a discrete bottom bar shaded by how
    booked that slot already is (vs. instructor/aircraft capacity), nudging students
    toward freer hours.
- **Auto-scheduler (linear program)** — a PuLP/CBC integer program solves the
  many-students/few-resources matching fairly (everyone's first hours weighted
  highest), with toggles to keep-vs-rebuild, distribute over planes, distribute over
  the week, and split per-student hours. Honours **exact fractional requests** (a
  3.5h request is scheduled as 3.5h, not rounded). Preview → apply.
- **Aircraft-centric planning board** — one grid per aircraft showing every
  student's availability at once (overlaps in red), drag-to-reschedule, instructor
  double-booking guard, and a per-student requested-hours cap (the assign modal
  disables over-limit end times and blocks save). Mobile shows one day at a time via
  a day selector.
- **EASA pilot logbook** — instructors log flown hours per student/day (total
  auto-calculated from times, shown as H:MM); PPL-A flights get the EASA exercises
  multi-select; filter by student/period; sortable, responsive DataTables.
- **Roles**: Student, Instructor, **Manager**, Admin. Planners (admin + manager)
  build the schedule; instructors log flights and see their assignments. Managers
  can also reach **Settings** (operating hours/days, ICAO, airfield info) — only the
  API key, weather URL and map URLs stay admin-only.
- **Dashboard**: stats, upcoming flights, live weather, METAR/TAF, NOTAMs, and an
  editable home-airfield info card + embedded map (bilingual).
- **Airfield weather station**: live data from a local Ecowitt station.
- **METAR / TAF**: CheckWX API with nearest-station fallback; cached hourly.
- **NOTAMs**: live from ROMATSA.
- **Resilient weather/NOTAM cache**: a transient upstream failure never wipes good
  data — the last successful METAR/TAF/NOTAMs keep showing (flagged stale) instead
  of an error.
- **LT / UTC toggle** across the whole app, with a **UTC label shown next to the
  times** (planning board, availability grid, booking lists, sun/night times) so
  it's always clear which zone is displayed.
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
flask --app run seed                # creates default accounts + sample aircraft
flask --app run seed-availability   # (optional) sample rule-compliant student availability
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

Managed via **Settings** in the web UI (admins + managers; API key / URLs are admin-only):

- **Operating hours (UTC)** — the daytime window students may mark availability in
- **Operating days** — per-weekday toggles; unused days drop off the grid and board
- **CheckWX API key** — free key from [checkwx.com](https://www.checkwx.com) for METAR/TAF/NOTAMs (admin-only)
- **ICAO airport code** — for weather/NOTAMs (e.g. LRPW falls back to nearest station LROP)
- **Airfield weather URL** — JSON endpoint for the local station (admin-only)
- **Home airfield info** — ARP coordinates, elevation, frequencies, airspace, procedures (shown on the dashboard)
- **Airfield map** — Google My Maps embed URL (separate RO / EN maps, admin-only)

Settings are stored in the database (the `.env` `CHECKWX_API_KEY` is only a
fallback). Saving triggers an immediate weather-cache refresh.

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

## Database backups

`scripts/backup_db.sh` writes a timestamped gzipped `pg_dump` to
`/home/ubuntu01/backups/aerovip/`, keeping the newest 30 (atomic write + rotation;
credentials read from `.env`). It's scheduled in the user crontab daily at 03:00.
Restore instructions are in `scripts/README-backup.md`.

```bash
scripts/backup_db.sh                  # run a backup now
flask --app run reseed-current-next   # drop closed-day bookings + reseed sample
                                      # availability for the current & next week,
                                      # honouring operating hours/days
```

## License

MIT
