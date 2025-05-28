from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager
from datetime import datetime, timezone # Wichtig für UTC

# Hilfstabelle für die Viele-zu-Viele-Beziehung zwischen User (Teamleiter) und Team
# Ein Teamleiter kann mehrere Teams leiten (obwohl in deinem Fall 1:1),
# und ein Team kann (theoretisch) mehrere Leiter haben. Für dein Szenario (1 TL pro Team) ist es einfacher.
# Wir machen es so, dass ein Team EINEN Teamleiter hat.

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), nullable=False, default='Teammitglied') # Rollen: Admin, Projektleiter, Qualitätsmanager, SalesCoach, Trainer, Teamleiter
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True) # Nur für Teamleiter relevant
    
    # Beziehung: Ein User (als Coach) kann viele Coachings durchführen
    coachings_done = db.relationship('Coaching', foreign_keys='Coaching.coach_id', backref='coach', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

class Team(db.Model):
    __tablename__ = 'teams'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    team_leader_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # FK zum User, der Teamleiter ist
    
    team_leader = db.relationship('User', backref=db.backref('led_team', uselist=False)) # Ein Team hat einen Leiter
    members = db.relationship('TeamMember', backref='team', lazy='dynamic')
    
    def __repr__(self):
        return f'<Team {self.name}>'

class TeamMember(db.Model):
    __tablename__ = 'team_members'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    
    # Beziehung: Ein Teammitglied kann viele Coachings erhalten
    coachings_received = db.relationship('Coaching', backref='team_member_coached', lazy='dynamic')

    def __repr__(self):
        return f'<TeamMember {self.name} (Team ID: {self.team_id})>'

class Coaching(db.Model):
    __tablename__ = 'coachings'
    id = db.Column(db.Integer, primary_key=True)
    team_member_id = db.Column(db.Integer, db.ForeignKey('team_members.id'), nullable=False)
    coach_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False) # Der User, der das Coaching durchgeführt hat
    coaching_date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)) # UTC Zeit!
    coaching_style = db.Column(db.String(50)) # "Side-by-Side" oder "TCAP"
    tcap_id = db.Column(db.String(50), nullable=True)
    
    # Leitfaden Checkmarks (Ja, Nein, k.A.)
    # Wir verwenden Strings, um die drei Zustände abzubilden. Könnte auch ENUM sein.
    # Boolean wäre: True (erfüllt), False (nicht erfüllt), None (k.A.).
    # Für Einfachheit hier Strings, die im Formular als Select-Felder dargestellt werden.
    leitfaden_begruessung = db.Column(db.String(10), default="k.A.")
    leitfaden_legitimation = db.Column(db.String(10), default="k.A.")
    leitfaden_pka = db.Column(db.String(10), default="k.A.")
    leitfaden_kek = db.Column(db.String(10), default="k.A.")
    leitfaden_angebot = db.Column(db.String(10), default="k.A.")
    leitfaden_zusammenfassung = db.Column(db.String(10), default="k.A.")
    leitfaden_kzb = db.Column(db.String(10), default="k.A.")
    
    performance_mark = db.Column(db.Integer) # Note 0-10
    time_spent = db.Column(db.Integer) # In Minuten
    project_leader_notes = db.Column(db.Text, nullable=True)
    
    # Score wird berechnet, nicht direkt gespeichert, aber wir könnten es tun für Performance.
    # Hier verzichten wir erstmal darauf und berechnen es bei Bedarf.

    def __repr__(self):
        return f'<Coaching {self.id} for TeamMember {self.team_member_id} on {self.coaching_date}>'

    @property
    def leitfaden_score_details(self):
        leitfaden_fields = [
            self.leitfaden_begruessung, self.leitfaden_legitimation, self.leitfaden_pka,
            self.leitfaden_kek, self.leitfaden_angebot, self.leitfaden_zusammenfassung, self.leitfaden_kzb
        ]
        ja_count = sum(1 for x in leitfaden_fields if x == "Ja")
        total_relevant_fields = sum(1 for x in leitfaden_fields if x != "k.A.")
        
        if total_relevant_fields == 0:
            return 0.0 # Oder einen anderen Standardwert, wenn keine relevanten Felder bewertet wurden
        
        return (ja_count / total_relevant_fields) * 100 # Gibt Prozent zurück

    @property
    def overall_score(self):
        leitfaden_percentage = self.leitfaden_score_details
        
        # Gewichtung: 80% Performance Mark, 20% Leitfaden
        # Performance Mark ist 0-10, also (mark/10 * 100) für Prozent
        performance_percentage = (self.performance_mark / 10) * 100 if self.performance_mark is not None else 0
        
        score = (performance_percentage * 0.8) + (leitfaden_percentage * 0.2)
        return round(score, 2) # Auf 2 Nachkommastellen runden