from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config import Config
import os

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login' # Route, zu der umgeleitet wird, wenn Zugriff verweigert
login_manager.login_message = "Bitte melden Sie sich an, um auf diese Seite zuzugreifen."
login_manager.login_message_category = "info" # Für Bootstrap-Styling von Flash-Nachrichten

migrate = Migrate()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    # Blueprints registrieren (unsere "Module" der App)
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.main_routes import bp as main_bp # Wir nennen die Datei main_routes.py für die Hauptlogik
    app.register_blueprint(main_bp)

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    # Stelle sicher, dass der instance Ordner existiert (obwohl wir ihn nicht stark nutzen werden, wenn die DB auf Railway ist)
    # In unserem Fall wird die DB nicht lokal sein, aber Flask könnte es für andere Dinge nutzen.
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    return app

# Importiere Modelle am Ende, um zirkuläre Importe zu vermeiden
from app import models