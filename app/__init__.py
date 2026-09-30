import os
import time
from flask import Flask, redirect, url_for, session, g
import sqlite3
from sqlalchemy import event
from sqlalchemy.engine import Engine
from config import config, basedir
from app.extensions import db, migrate, init_csrf
from app.models import User
from app.routes import all_blueprints

# Optimize SQLite with Write-Ahead Logging (WAL) and concurrent busy timeout
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.close()

def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config.get(config_name, config['default']))

    # Ensure instance and database directories exist
    try:
        os.makedirs(app.instance_path, exist_ok=True)
        os.makedirs(os.path.join(basedir, "database"), exist_ok=True)
    except OSError:
        pass

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    init_csrf(app)

    @app.before_request
    def record_start_time():
        g.start_time = time.perf_counter()

    # Global template context processor with request-level caching
    @app.context_processor
    def inject_global_vars():
        from app.helpers import get_current_user
        return dict(current_user=get_current_user())

    @app.after_request
    def add_db_header(response):
        db_uri = str(app.config.get('SQLALCHEMY_DATABASE_URI', ''))
        response.headers['X-EMR-Database'] = 'sqlite' if 'sqlite' in db_uri else 'mysql'
        if hasattr(g, 'start_time'):
            elapsed = (time.perf_counter() - g.start_time) * 1000
            response.headers['X-Server-Execution-Time'] = f"{elapsed:.2f}ms"
        return response

    # Register all consolidated Blueprints from routes.py
    for bp in all_blueprints:
        app.register_blueprint(bp)

    @app.route('/')
    def root():
        if '_account_id' in session or '_user_id' in session:
            return redirect(url_for('patients.patients_list'))
        return redirect(url_for('auth.login'))

    return app
