import secrets
from flask import session, request, abort, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']

def init_csrf(app):
    @app.before_request
    def check_csrf():
        if not current_app.config.get('WTF_CSRF_ENABLED', True):
            return
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            # Allow skipping if explicitly flagged (e.g. specific webhook if any)
            token = request.form.get('csrf_token') or request.headers.get('X-CSRFToken')
            expected = session.get('_csrf_token')
            if not expected or not token or not secrets.compare_digest(token, expected):
                abort(400, description="Invalid or missing CSRF token.")

    @app.context_processor
    def inject_csrf():
        return dict(csrf_token=generate_csrf_token)

