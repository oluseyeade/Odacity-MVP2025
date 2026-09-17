from flask import Flask
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate


from pkg.config import ProConfig

csrf = CSRFProtect()



def create_app():
    from pkg.models import db
    app= Flask(__name__,instance_relative_config=True)
    app.config.from_pyfile('config.py', silent=True)
    app.config.from_object(ProConfig)

   
    db.init_app(app)
    migraqte = Migrate(app,db)
    csrf.init_app(app)

    return app
app = create_app()
from pkg import user_routes, admin_routes, forms
