import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
    SQLALCHEMY_DATABASE_URI = os.environ.get('SQLALCHEMY_DATABASE_URI', 'sqlite:///edgar.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 300
    # SSL verification for SEC EDGAR requests. Always True in production.
    # Override via EDGAR_VERIFY_SSL=false env var only in controlled environments.
    EDGAR_VERIFY_SSL: bool = os.environ.get('EDGAR_VERIFY_SSL', 'true').lower() not in ('false', '0', 'no')
    # Base directory for storing downloaded SEC filing PDFs.
    FILING_STORAGE_PATH: str = os.environ.get('FILING_STORAGE_PATH', 'instance/filings')


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    EDGAR_VERIFY_SSL: bool = os.environ.get('EDGAR_VERIFY_SSL', 'true').lower() not in ('false', '0', 'no')


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SESSION_COOKIE_SECURE = False
    RATELIMIT_STORAGE_URI = 'memory://'


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True


config_map = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
}
