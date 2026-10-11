import os
import secrets
import urllib.parse

basedir = os.path.abspath(os.path.dirname(__file__))


def load_dotenv_file(filepath):
    """Lightweight built-in .env loader with zero external dependencies."""
    if not os.path.exists(filepath):
        return
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, val = line.split('=', 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


load_dotenv_file(os.path.join(basedir, '.env'))

# MySQL / MariaDB Credentials (loaded strictly from environment / .env)
DB_USER = os.environ.get('DB_USER', '')
DB_PASS = urllib.parse.quote_plus(os.environ.get('DB_PASSWORD', ''))
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '3306')
DB_NAME = os.environ.get('DB_NAME', 'clinic_emr')

MYSQL_DATABASE_URI = (
    f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    if DB_USER else ""
)

# SQLite Database Path in 'database' folder
SQLITE_DATABASE_PATH = os.path.join(basedir, "database", "emr.sqlite3")
SQLITE_DATABASE_URI = f"sqlite:///{SQLITE_DATABASE_PATH}"

# Primary URI: Default to high-performance local SQLite database unless USE_MARIADB=1 is set
if os.environ.get('USE_MARIADB') == '1' and MYSQL_DATABASE_URI:
    DEFAULT_DATABASE_URI = os.environ.get('DATABASE_URL', MYSQL_DATABASE_URI)
else:
    DEFAULT_DATABASE_URI = os.environ.get('SQLITE_URL', SQLITE_DATABASE_URI)

# SQLite vs MySQL Engine options
if DEFAULT_DATABASE_URI.startswith('sqlite'):
    DEFAULT_ENGINE_OPTIONS = {
        'connect_args': {'timeout': 15}
    }
else:
    DEFAULT_ENGINE_OPTIONS = {
        'connect_args': {'connect_timeout': 30},
        'pool_pre_ping': True,
        'pool_recycle': 280
    }


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ITEMS_PER_PAGE = 15
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SEND_FILE_MAX_AGE_DEFAULT = 43200  # 12 hours browser caching for static CSS/JS
    SQLALCHEMY_DATABASE_URI = DEFAULT_DATABASE_URI
    SQLALCHEMY_ENGINE_OPTIONS = DEFAULT_ENGINE_OPTIONS


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'


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
