import os
from dotenv import load_dotenv

# Lade Umgebungsvariablen aus der .env Datei (primär für lokale Entwicklung)
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'ein-sehr-geheimer-fallback-schluessel'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False # Deaktiviert eine Flask-SQLAlchemy Funktion, die wir nicht brauchen und Performance kostet