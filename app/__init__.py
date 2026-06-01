import os
import subprocess
from datetime import datetime
from flask import Flask, session, request, url_for
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


def _compute_version():
    """Version string derived from git — bumps on every commit (count + short SHA).
    Computed once at startup; a deploy restarts the service so it refreshes."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        count = subprocess.check_output(['git', 'rev-list', '--count', 'HEAD'],
                                        cwd=root, stderr=subprocess.DEVNULL, timeout=3).decode().strip()
        return count
    except Exception:
        return 'dev'


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config['APP_VERSION'] = _compute_version()

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

    # Cache-busting: append the file's mtime to static URLs so browsers (and the
    # service worker) fetch fresh CSS/JS whenever a file changes, despite the
    # long/immutable cache headers on /static/.
    @app.url_defaults
    def _static_cache_bust(endpoint, values):
        if endpoint == 'static' and 'filename' in values:
            try:
                fp = os.path.join(app.static_folder, values['filename'])
                values['v'] = int(os.path.getmtime(fp))
            except OSError:
                pass

    # asset_url(): fingerprinted path (/aerovip/assets/<mtime>/...) that survives the
    # Cloudflare edge cache (which ignores query strings).
    @app.context_processor
    def inject_asset_url():
        def asset_url(filename):
            try:
                v = int(os.path.getmtime(os.path.join(app.static_folder, filename)))
            except OSError:
                v = 0
            return url_for('main.asset', v=v, filename=filename)
        return dict(asset_url=asset_url)

    @app.context_processor
    def inject_version():
        return dict(app_version=app.config.get('APP_VERSION', 'dev'),
                    current_year=datetime.utcnow().year)

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
        from flask_login import current_user
        # Only planners (admin/manager) get the UTC option; everyone else is LT-only.
        is_planner = getattr(current_user, 'is_planner', False)
        mode = session.get('tz', 'lt') if is_planner else 'lt'

        def disp(dt, fmt='%H:%M'):
            """Format a (local) booking datetime, converting to UTC when in UTC mode."""
            if dt is None:
                return ''
            if mode == 'utc':
                return weekutils.to_utc(dt).strftime(fmt)
            return dt.strftime(fmt)

        # Appended after displayed times so it's clear they're UTC when UTC is selected.
        tz_suffix = ' UTC' if mode == 'utc' else ''
        return dict(tz_mode=mode, disp=disp, tz_suffix=tz_suffix)

    from app.routes import auth, main, admin, scheduling, aircraft, logbook, documents
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(scheduling.bp)
    app.register_blueprint(aircraft.bp)
    app.register_blueprint(logbook.bp)
    app.register_blueprint(documents.bp)

    # Start background weather/NOTAMs cache refresh thread
    from app.weather_cache import start_background_refresh
    start_background_refresh(app)

    return app
