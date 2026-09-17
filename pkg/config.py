import os

def _get_database_uri():
    db_url = os.environ.get('DATABASE_URL', 'mysql+mysqlconnector://root:rootpassword@127.0.0.1/odasitydb')
    if db_url.startswith('mysql://'):
        return 'mysql+mysqlconnector://' + db_url[8:]
    return db_url

class GeneralConfig(object):
    SECRET_KEY = os.environ.get('SECRET_KEY', 'trMNfGHpxif25uzIYwU')
    TECH_SUPPORT = "0809999999"

class ProConfig(GeneralConfig):
    SECRET_KEY = os.environ.get('SECRET_KEY', 'live_trMNfGHpxif25uzIYwU')
    ADMIN_EMAIL = "live@admin.com"
    SQLALCHEMY_DATABASE_URI = _get_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class DevConfig(GeneralConfig):
    SECRET_KEY = "dev_trMNfGHpxif25uzIYwU"
    SQLALCHEMY_DATABASE_URI = _get_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class TestConfig(GeneralConfig):
    ADMIN_EMAIL = "test@admin.com"