import os
from flask import Flask, redirect, url_for, session
from config import config
from app.extensions import db, migrate, init_csrf
from app.models import User
from app.routes import all_blueprints

def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config.get(config_name, config['default']))

    # Ensure instance directory exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    init_csrf(app)

    # Global template context processor
    @app.context_processor
    def inject_global_vars():
        user = None
        if '_user_id' in session:
            user = db.session.get(User, session['_user_id'])
        return dict(current_user=user)

    # Register all consolidated Blueprints from routes.py
    for bp in all_blueprints:
        app.register_blueprint(bp)

    @app.route('/')
    def root():
        if '_user_id' in session:
            return redirect(url_for('patients.patients_list'))
        return redirect(url_for('auth.login'))

    return app
