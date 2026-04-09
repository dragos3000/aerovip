# Aero Vip Academy - Flight School Scheduling App

A flight school scheduling application built with Flask and PostgreSQL for managing students, instructors, aircraft, and flight bookings.

## Features

- **User Roles**: Student, Instructor, Admin with role-based access control
- **Flight Scheduling**: Calendar-based booking with double-booking prevention (aircraft, instructor, student)
- **Aircraft Management**: Full CRUD for fleet management
- **Dashboard**: Stats overview with live weather data
- **Airfield Weather Station**: Live data from local Ecowitt station (configurable URL)
- **METAR / TAF**: Aviation weather via CheckWX API with automatic nearest-station fallback
- **NOTAMs**: Live NOTAMs from ROMATSA (flightplan.romatsa.ro)
- **Bilingual**: Romanian / English language selector
- **Responsive UI**: Bootstrap 5 + DataTables Responsive + FullCalendar
- **Production Ready**: Gunicorn + Nginx + SSL (Let's Encrypt)

## Tech Stack

- **Backend**: Python Flask, SQLAlchemy, Flask-Login, Flask-Migrate
- **Database**: PostgreSQL
- **Frontend**: Bootstrap 5, DataTables, FullCalendar, Bootstrap Icons
- **Deployment**: Gunicorn, Nginx, systemd, Let's Encrypt SSL

## Quick Start

```bash
# Clone and setup
git clone https://github.com/dragos3000/aerovip.git
cd aerovip
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your database credentials and API keys

# Database setup
createdb aerovip
flask --app run db init
flask --app run db migrate -m "Initial"
flask --app run db upgrade
flask --app run seed

# Run development server
python run.py
```

## Default Accounts

| Role       | Email                  | Password       |
|------------|------------------------|----------------|
| Admin      | admin@aerovip.ro       | admin123        |
| Instructor | instructor@aerovip.ro  | instructor123   |
| Student    | student@aerovip.ro     | student123      |

## Configuration

Settings are managed via **Admin > Settings** in the web UI:

- **CheckWX API Key**: Get a free key from [checkwx.com](https://www.checkwx.com) for METAR/TAF
- **ICAO Airport Code**: Default airport for weather and NOTAMs (e.g. LROP, LRBS)
- **Airfield Weather URL**: JSON endpoint for local weather station

## Production Deployment

```bash
sudo bash deploy.sh
```

This will set up PostgreSQL, Gunicorn (port 8086), Nginx reverse proxy with SSL on `start-line.ro/aerovip`.

## License

MIT
