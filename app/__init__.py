import logging
import os
from flask import Flask, jsonify, redirect, request, url_for
from flask_admin import Admin
from flask_bootstrap import Bootstrap
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

from app.configuration import config_map

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
bootstrap = Bootstrap()
cache = Cache()
limiter = Limiter(key_func=get_remote_address)
admin = Admin(name='EDGAR Stock Data')


def create_app(config_name: str | None = None) -> Flask:
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'development')

    app = Flask(__name__)
    app.config.from_object(config_map[config_name])

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    bootstrap.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'

    admin.init_app(app)

    # LoginManager unauthorized handler
    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Authentication required.'}), 401
        return redirect(url_for('main.login'))

    # Security headers
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "object-src 'none'; "
            "frame-ancestors 'none';"
        )
        return response

    # Error handlers
    @app.errorhandler(400)
    def bad_request(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Bad request.'}), 400
        return e

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Not found.'}), 404
        return e

    @app.errorhandler(500)
    def internal_error(e):
        logging.getLogger('app').error('Internal server error: %s', e)
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Internal server error.'}), 500
        return e

    from app import models  # noqa: F401
    from app.views import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from app.admin_views import register_admin_views
    register_admin_views(admin)

    # Auto-apply pending migrations on startup so the DB is always current.
    # This means flask db upgrade does not need to be run manually after
    # deleting the database or cloning the repo for the first time.
    if not app.testing:
        with app.app_context():
            from flask_migrate import upgrade as db_upgrade
            db_upgrade()

    return app
