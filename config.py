import os
import urllib.parse

basedir = os.path.abspath(os.path.dirname(__file__))

# Waifly Database Credentials
WAIFLY_USER = os.environ.get('DB_USER', 'u10258_wOmSdH3una')
WAIFLY_PASS = urllib.parse.quote_plus(os.environ.get('DB_PASSWORD', 'YEPDUM6KA7u3@kFX@nR8r=0V'))
WAIFLY_HOST = os.environ.get('DB_HOST', 'db.waifly.com')
WAIFLY_PORT = os.environ.get('DB_PORT', '3306')
WAIFLY_NAME = os.environ.get('DB_NAME', 's10258_clinic_emr')

WAIFLY_DATABASE_URI = (
    f"mysql+pymysql://{WAIFLY_USER}:{WAIFLY_PASS}@{WAIFLY_HOST}:{WAIFLY_PORT}/{WAIFLY_NAME}?charset=utf8mb4"
)

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'myanmar-emr-super-secret-key-development-only-2026')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ITEMS_PER_PAGE = 15
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {'connect_timeout': 30},
        'pool_pre_ping': True,
        'pool_recycle': 280
    }

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        WAIFLY_DATABASE_URI if os.environ.get('USE_LOCAL_SQLITE') != '1' else f'sqlite:///{os.path.join(basedir, "instance", "emr.sqlite3")}'
    )

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', WAIFLY_DATABASE_URI)
    SESSION_COOKIE_SECURE = False

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'
    SQLALCHEMY_ENGINE_OPTIONS = {}

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
