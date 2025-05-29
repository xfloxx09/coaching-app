# app/__init__.py
print("<<<< START __init__.py wird GELADEN >>>>")

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config import Config # Deine Konfigurationsklasse
import os
from datetime import datetime, timezone # timezone für UTC und datetime für current_year
import pytz # Für Zeitzonenkonvertierung
# from calendar import monthrange # Wird jetzt in main_routes.py importiert, wo es gebraucht wird

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login' # Route, zu der umgeleitet wird, wenn Zugriff verweigert
login_manager.login_message = "Bitte melden Sie sich an, um auf diese Seite zuzugreifen."
login_manager.login_message_category = "info" # Für Bootstrap-Styling von Flash-Nachrichten

migrate = Migrate()

# bootstrap = Bootstrap() # Auskommentiert, da wir es nicht aktiv nutzen

def create_app(config_class=Config):
    print("<<<< create_app() WIRD AUFGERUFEN (__init__.py) >>>>")
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    print("<<<< db.init_app() VORBEI (__init__.py) >>>>")
    login_manager.init_app(app)
    migrate.init_app(app, db)
    # bootstrap.init_app(app) # Auskommentiert

    # Blueprints registrieren
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    print("<<<< auth_bp REGISTRIERT (__init__.py) >>>>")

    from app.main_routes import bp as main_bp 
    app.register_blueprint(main_bp)
    print("<<<< main_bp REGISTRIERT (__init__.py) >>>>")

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    print("<<<< admin_bp REGISTRIERT (__init__.py) >>>>")
    
    # Kontextprozessor für globale Variablen in Templates (z.B. aktuelles Jahr)
    @app.context_processor
    def inject_current_year():
        # print("<<<< inject_current_year WIRD AUFGERUFEN >>>>") # Optionaler Debug-Print
        return {'current_year': datetime.utcnow().year}

    # Benutzerdefinierter Jinja-Filter für Athener Zeit
    @app.template_filter('athens_time')
    def format_athens_time(utc_dt, fmt='%d.%m.%Y %H:%M'):
        if not utc_dt:
            return ""
        if not isinstance(utc_dt, datetime):
            # Versuche, es zu parsen, falls es ein String ist (ISO-Format oft von DBs)
            if isinstance(utc_dt, str):
                try:
                    utc_dt = datetime.fromisoformat(utc_dt.replace('Z', '+00:00'))
                except ValueError:
                    try: # Fallback für Formate ohne Millisekunden oder Z
                        utc_dt = datetime.strptime(utc_dt, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                         return str(utc_dt) # Wenn alles fehlschlägt, gib Original zurück
            else:
                return str(utc_dt) 

        # Stelle sicher, dass das Datum timezone-aware ist (UTC)
        if utc_dt.tzinfo is None or utc_dt.tzinfo.utcoffset(utc_dt) is None:
            utc_dt = utc_dt.replace(tzinfo=timezone.utc) # Mache es UTC-aware, falls es naiv ist
        
        athens_tz = pytz.timezone('Europe/Athens')
        try:
            local_dt = utc_dt.astimezone(athens_tz)
            return local_dt.strftime(fmt)
        except Exception as e:
            # print(f"Fehler bei Zeitzonenkonvertierung für {utc_dt}: {e}") # Für Debugging
            # Fallback, falls Konvertierung fehlschlägt (z.B. ungültiges Datum für pytz)
            try:
                return utc_dt.strftime(fmt) + " (UTC?)" 
            except:
                return str(utc_dt) # Letzter Fallback

    # Stelle sicher, dass der instance Ordner existiert
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    
    print("<<<< VOR Import von app.models in create_app (__init__.py) >>>>")
    from app import models # Dieser Import ist entscheidend, damit Modelle db kennen
    print("<<<< NACH Import von app.models in create_app (__init__.py) >>>>")

    print("<<<< create_app() FERTIG, app wird zurückgegeben (__init__.py) >>>>")
    return app

# Der globale Import von 'from app import models' hier unten ist oft wichtig für
# Flask CLI Befehle wie 'flask shell' oder 'flask db', damit die Modelle
# global bekannt sind, bevor die App vollständig durch einen Request initialisiert wird.
# Wenn der Import innerhalb von create_app() nicht für alle CLI-Tools ausreicht,
# kann dieser globale Import helfen. Flask-Migrate benötigt oft, dass die Modelle
# beim Import von 'app' bereits bekannt sind.
print("<<<< VOR globalem Import von app.models am Ende von __init__.py >>>>")
from app import models 
print("<<<< NACH globalem Import von app.models am Ende von __init__.py >>>>")

print("<<<< ENDE __init__.py wurde GELADEN >>>>")
