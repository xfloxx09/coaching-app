from functools import wraps
from flask_login import current_user
from flask import abort

def role_required(role_name_or_list):
    """
    Decorator, der prüft, ob der aktuelle Benutzer die erforderliche Rolle hat.
    Akzeptiert einen einzelnen Rollennamen oder eine Liste von Rollennamen.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return abort(401) # Nicht autorisiert
            
            required_roles = []
            if isinstance(role_name_or_list, str):
                required_roles.append(role_name_or_list)
            elif isinstance(role_name_or_list, list):
                required_roles = role_name_or_list
            else:
                return abort(500) # Serverfehler, falsche Konfiguration des Decorators

            if current_user.role not in required_roles:
                return abort(403) # Verboten
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Konstanten für Rollen (um Tippfehler zu vermeiden)
ROLE_ADMIN = 'Admin'
ROLE_PROJEKTLEITER = 'Projektleiter'
ROLE_QM = 'Qualitätsmanager'
ROLE_SALESCOACH = 'SalesCoach'
ROLE_TRAINER = 'Trainer'
ROLE_TEAMLEITER = 'Teamleiter'
ROLE_ABTEILUNGSLEITER = 'Abteilungsleiter'
# Teammitglied ist keine Rolle, die spezielle Rechte hat, sondern eher der Standard.
