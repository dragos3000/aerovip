from flask import Flask, session, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Handle reverse proxy headers (X-Forwarded-For, X-Forwarded-Proto, X-Forwarded-Prefix)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_prefix=1)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    # Format decimal flight hours as H:MM (e.g. 1.75 -> "1:45")
    def format_hm(hours):
        try:
            total = int(round(float(hours or 0) * 60))
        except (TypeError, ValueError):
            total = 0
        return f'{total // 60}:{total % 60:02d}'
    app.jinja_env.filters['hm'] = format_hm

    from app.models import User
    from app.translations import get_translation

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.before_request
    def set_language():
        if 'lang' not in session:
            session['lang'] = 'ro'

    @app.context_processor
    def inject_translations():
        lang = session.get('lang', 'ro')

        def t(key):
            return get_translation(key, lang)

        return dict(t=t, current_lang=lang)

    @app.context_processor
    def inject_tz():
        from app import weekutils
        mode = session.get('tz', 'lt')

        def disp(dt, fmt='%H:%M'):
            """Format a (local) booking datetime, converting to UTC when in UTC mode."""
            if dt is None:
                return ''
            if mode == 'utc':
                return weekutils.to_utc(dt).strftime(fmt)
            return dt.strftime(fmt)

        return dict(tz_mode=mode, disp=disp)

    from app.routes import auth, main, admin, scheduling, aircraft, logbook
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(scheduling.bp)
    app.register_blueprint(aircraft.bp)
    app.register_blueprint(logbook.bp)

    # Start background weather/NOTAMs cache refresh thread
    from app.weather_cache import start_background_refresh
    start_background_refresh(app)

    return app
