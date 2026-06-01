import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql://aerovip:aerovip@localhost:5432/aerovip')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CHECKWX_API_KEY = os.environ.get('CHECKWX_API_KEY', '')
    ICAO_AIRPORT = os.environ.get('ICAO_AIRPORT', 'LRBS')

    # The app shares start-line.ro with another Flask app under /app/, both of which
    # defaulted to the cookie name 'session' — so their sessions collided and logged
    # users out. A unique name fixes it (no path scoping needed, avoids prefix issues).
    SESSION_COOKIE_NAME = 'aerovip_session'
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Max upload size for student documents (10 MB).
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
