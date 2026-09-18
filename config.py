import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'myanmar-emr-super-secret-key-development-only-2026')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ITEMS_PER_PAGE = 15
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

class DevelopmentConfig(Config):
    DEBUG = True
    # Portable to MySQL later. Default development is SQLite in instance/
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        f'sqlite:///{os.path.join(basedir, "instance", "emr.sqlite3")}'
    )

class ProductionConfig(Config):
    DEBUG = False
    # In production on Waifly, this will be mysql+pymysql://user:password@host/dbname
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SESSION_COOKIE_SECURE = True

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

