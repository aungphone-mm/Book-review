import os

# Render sets this on every deployed instance; locally it is absent
IS_DEPLOYED = os.environ.get('RENDER') == 'true'

def database_uri():
    url = os.environ.get('DATABASE_URL')
    if not url:
        if IS_DEPLOYED:
            raise RuntimeError('DATABASE_URL is not set; the SQLite fallback cannot be used on Render')
        return 'sqlite:///book_reviews.db'
    # Render and Heroku hand out postgres:// URLs, which SQLAlchemy 1.4+ refuses
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return url

def secret(name, dev_fallback):
    value = os.environ.get(name)
    if value:
        return value
    if IS_DEPLOYED:
        raise RuntimeError('%s is not set; refusing to start with the development fallback' % name)
    return dev_fallback

class Config:
    SECRET_KEY = secret('SECRET_KEY', 'dev-only-secret-key')
    SQLALCHEMY_DATABASE_URI = database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = secret('JWT_SECRET_KEY', 'dev-only-jwt-secret-key')
    # Neon suspends an idle compute and drops its connections. Without a
    # liveness check the pool hands a dead socket to the next request and it
    # fails with "server closed the connection unexpectedly"; pre_ping costs
    # one round trip and retries transparently instead.
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
