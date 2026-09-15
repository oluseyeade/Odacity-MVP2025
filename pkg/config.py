import os

class GeneralConfig(object):
    SECRET_KEY = os.environ.get('SECRET_KEY', 'trMNfGHpxif25uzIYwU')
    TECH_SUPPORT = "0809999999"

class ProConfig(GeneralConfig):
    SECRET_KEY = os.environ.get('SECRET_KEY', 'live_trMNfGHpxif25uzIYwU')
    ADMIN_EMAIL = "live@admin.com"
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'mysql+mysqlconnector://root:rootpassword@127.0.0.1/odasitydb')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class DevConfig(GeneralConfig):
    SECRET_KEY = "dev_trMNfGHpxif25uzIYwU"
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'mysql+mysqlconnector://root:rootpassword@127.0.0.1/odasitydb')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class TestConfig(GeneralConfig):
    ADMIN_EMAIL = "test@admin.com"