# app/__init__.py
print("<<<< START __init__.py wird GELADEN >>>>") # Dein Debug-Print, falls noch da

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config import Config
import os
from datetime import datetime # <--- WICHTIG: Import für datetime hinzufügen

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login' 
login_manager.login_message = "Bitte melden Sie sich an, um auf diese Seite zuzugreifen."
login_manager.login_message_category = "info"

migrate = Migrate()

def create_app(config_class=Config):
    print("<<<< create_app() WIRD AUFGERUFEN (__init__.py) >>>>") # Dein Debug-Print
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    print("<<<< db.init_app() VORBEI (__init__.py) >>>>") # Dein Debug-Print
    login_manager.init_app(app)
    migrate.init_app(app, db)

    # Blueprints registrieren
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    print("<<<< auth_bp REGISTRIERT (__init__.py) >>>>") # Dein Debug-Print

    from app.main_routes import bp as main_bp
    app.register_blueprint(main_bp)
    print("<<<< main_bp REGISTRIERT (__init__.py) >>>>") # Dein Debug-Print

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    print("<<<< admin_bp REGISTRIERT (__init__.py) >>>>") # Dein Debug-Print
    
    # Kontextprozessor für globale Variablen in Templates
    @app.context_processor  # <--- HIER IST ER WIEDER
    def inject_current_year():
        print("<<<< inject_current_year WIRD AUFGERUFEN >>>>") # Optionaler Debug-Print
        return {'current_year': datetime.utcnow().year}

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    
    print("<<<< VOR Import von app.models in create_app (__init__.py) >>>>") # Dein Debug-Print
    from app import models # Dieser Import ist entscheidend
    print("<<<< NACH Import von app.models in create_app (__init__.py) >>>>") # Dein Debug-Print

    print("<<<< create_app() FERTIG, app wird zurückgegeben (__init__.py) >>>>") # Dein Debug-Print
    return app

# Der globale Import von 'from app import models' hier unten ist für die Flask-Shell und
# Flask-Migrate oft wichtig, damit die Modelle global erkannt werden, bevor die App vollständig
# durch einen Request initialisiert wird.
# Wenn `flask db init/migrate/upgrade` oder `flask shell` ohne ihn Probleme machen,
# füge ihn wieder hinzu. Für den reinen App-Lauf sollte der Import in `create_app` reichen.
# Für maximale Kompatibilität mit den CLI-Tools ist er hier oft besser aufgehoben.
print("<<<< VOR globalem Import von app.models am Ende von __init__.py >>>>") # Dein Debug-Print
from app import models # <--- DIESEN WIEDER EINFÜGEN, FALLS ENTFERNT
print("<<<< NACH globalem Import von app.models am Ende von __init__.py >>>>") # Dein Debug-Print