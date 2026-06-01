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
  - **Day vs night windows** — day-type hours (PPL-A / Buildup / AUPRT) must be
    backed by **daytime** cells inside the configured operating window (set in UTC);
    Night hours must be backed by **after-sunset** cells. The night window stays
    pickable outside operating hours because night training is flown at a non-stop
    airport elsewhere. Validated per-window (day-types can't sit in the night window
    and vice-versa).
  - **Operating days** — only the configured operating weekdays are pickable; unused
    days are removed from both the availability grid and the planning board.
  - **No past weeks** — the current week is the earliest submittable; past weeks are
    read-only (grid locked, Save disabled) and the ◀ nav stops at the current week.
  - **Locked once planned** — once a student has bookings for a week, their
    availability for that week is locked (read-only) and can't be changed.
- **Student schedule** shows a notice that the start time is the takeoff time (be at
  the airfield 30 minutes before).
  - **Busy-hour heat** — each hour cell is discreetly tinted by how contended it is —
    the number of *other* students who have booked **or** marked availability there,
    shaded against instructor/aircraft capacity — nudging students toward freer hours
    (works on the upcoming week before any flight is booked).
- **Auto-scheduler (linear program)** — a PuLP/CBC integer program solves the
  many-students/few-resources matching fairly (everyone's first hours weighted
  highest), with toggles to keep-vs-rebuild, distribute over planes, distribute over
  the week, and split per-student hours. Honours **exact fractional requests** (a
  3.5h request is scheduled as 3.5h, not rounded). A configurable **break between a
  student's flights** (minutes, default 30) is inserted by a re-pack pass that shifts
  later flights — cascading to any that would then overlap on the same plane/instructor
  — so nothing double-books. Preview → apply.
- **Aircraft-centric planning board** — one grid per aircraft showing every
  student's availability at once (overlaps in red), drag-to-reschedule, instructor
  double-booking guard, and a per-student requested-hours cap (the assign modal
  disables over-limit end times and blocks save). **Minute-precision times**: set a
  start to the minute and the end shifts to keep the same duration (9:00–10:00 →
  9:12–10:12). "Show availability" is on by default. Mobile shows one day at a time.
- **EASA pilot logbook** — instructors log flown hours per student/day (total
  auto-calculated from times, shown as H:MM); PPL-A flights get the EASA exercises
  multi-select; filter by student/period; sortable, responsive DataTables.
- **Student documents** — Licence, Medical, ID and RTF certificate uploads (PDF/image)
  with a **serial** and **expiry date**. Students manage their own; admins/managers
  manage any student's. Documents are **viewed in a modal** (PDF/image preview) and
  **editable** (type/serial/expiry, replace file); download/view is owner-or-planner
  only. Upload history is kept; the dashboard shows **expiry alerts** (expired /
  expiring) with a configurable warning window.
- **Accounts** — registration is **admin-approved**: new sign-ups are pending (can't
  log in) and the student is emailed on sign-up and again when approved. Password
  reset is by email — a "Forgot password?" link sends a time-limited (1 hour) reset
  link. SMTP is configured in the admin Settings UI; no user enumeration.
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
- **LT / UTC toggle** for **managers/admins only** (students and instructors always
  see local time, LT); with a **UTC label shown next to the times** (planning board,
  availability grid, booking lists, sun/night times) so the zone is always clear.
- **Bilingual**: Romanian / English.
- **Footer**: shows `© by Start-Line <year>` and a version number (`v<n>`) derived
  from the git commit count, so it bumps on every commit (refreshed on deploy/restart).
- **PWA**: installable, with an offline page and a network-first service worker.
- **Push notifications** (Web Push / VAPID, no native app): opt-in from a sidebar
  toggle; fires for **flight scheduled/changed**, **weekly plan published**, **document
  expiry** (daily check) and **account approved**. Works on Android/desktop from the
  browser; on iOS only when the PWA is **added to the Home Screen** (iOS 16.4+).
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
- **Document expiry warning (days)** — how early the dashboard warns before expiry
- **Email (SMTP)** — host / port / user / password / from / STARTTLS for password-reset
  emails (admin-only; password left untouched if the field is blank)
- **CheckWX API key** — free key from [checkwx.com](https://www.checkwx.com) for METAR/TAF/NOTAMs (admin-only)
- **ICAO airport code** — for weather/NOTAMs (e.g. LRPW falls back to nearest station LROP)
- **Airfield weather URL** — JSON endpoint for the local station (admin-only)
- **Home airfield info** — ARP coordinates, elevation, frequencies, airspace, procedures (shown on the dashboard)
- **Airfield map** — Google My Maps embed URL (separate RO / EN maps, admin-only)

- **Push notifications (VAPID)** — run `flask --app run gen-vapid` once to generate
  the key pair (stored in Settings); the public key + a `mailto:` contact show in the
  admin Settings (admin-only).

Settings are stored in the database (the `.env` `CHECKWX_API_KEY` is only a
fallback). Saving triggers an immediate weather-cache refresh. Uploaded documents are
stored under `instance/uploads/` (gitignored), max 10 MB, PDF/JPG/PNG.

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

`scripts/backup_db.sh` writes a timestamped gzipped `pg_dump` **and** a tarball of
`instance/uploads/` (student documents) to `/home/ubuntu01/backups/aerovip/`, keeping
the newest 30 of each (atomic write + rotation; credentials read from `.env`). It's
scheduled in the user crontab daily at 03:00. Restore instructions are in
`scripts/README-backup.md`.

```bash
scripts/backup_db.sh                  # run a backup now
flask --app run reseed-current-next   # drop closed-day bookings + reseed sample
                                      # availability for the current & next week,
                                      # honouring operating hours/days
```

## License

MIT
