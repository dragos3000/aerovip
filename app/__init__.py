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

    from app.routes import auth, main, admin, scheduling, aircraft
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(scheduling.bp)
    app.register_blueprint(aircraft.bp)

    # Start background weather/NOTAMs cache refresh thread
    from app.weather_cache import start_background_refresh
    start_background_refresh(app)

    return app
