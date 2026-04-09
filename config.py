import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql://aerovip:aerovip@localhost:5432/aerovip')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CHECKWX_API_KEY = os.environ.get('CHECKWX_API_KEY', '')
    ICAO_AIRPORT = os.environ.get('ICAO_AIRPORT', 'LRBS')
