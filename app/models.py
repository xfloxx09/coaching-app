# app/models.py
print("<<<< START models.py (KORRIGIERTE VERSION) GELADEN >>>>")

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager 
from datetime import datetime, timezone

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=False, nullable=True)
    password_hash = db.Column(db.String(256), nullable=True)
    role = db.Column(db.String(20), nullable=False, default='Teammitglied')
    team_id_if_leader = db.Column(db.Integer, db.ForeignKey('teams.id', name='fk_user_team_id_if_leader'), nullable=True) 
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
    team_leader_id = db.Column(db.Integer, db.ForeignKey('users.id', name='fk_team_team_leader_id'), nullable=True)
    team_leader = db.relationship(
        'User', 
        foreign_keys=[team_leader_id], 
        backref=db.backref('led_team_obj', uselist=False, lazy='joined')
    )
    members = db.relationship('TeamMember', backref='team', lazy='dynamic')
    def __repr__(self):
        return f'<Team {self.name}>'

class TeamMember(db.Model):
    __tablename__ = 'team_members'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id', name='fk_teammember_team_id'), nullable=False)
    coachings_received = db.relationship('Coaching', backref='team_member_coached', lazy='dynamic')
    def __repr__(self):
        return f'<TeamMember {self.name} (Team ID: {self.team_id})>'

class Coaching(db.Model):
    __tablename__ = 'coachings'
    id = db.Column(db.Integer, primary_key=True)
    team_member_id = db.Column(db.Integer, db.ForeignKey('team_members.id', name='fk_coaching_team_member_id'), nullable=False)
    coach_id = db.Column(db.Integer, db.ForeignKey('users.id', name='fk_coaching_coach_id'), nullable=False)
    coaching_date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    coaching_style = db.Column(db.String(50), nullable=True)
    tcap_id = db.Column(db.String(50), nullable=True)
    coaching_subject = db.Column(db.String(50), nullable=True) 
    coach_notes = db.Column(db.Text, nullable=True)
    
    leitfaden_begruessung = db.Column(db.String(10), default="k.A.", nullable=True)
    leitfaden_legitimation = db.Column(db.String(10), default="k.A.", nullable=True)
    leitfaden_pka = db.Column(db.String(10), default="k.A.", nullable=True)
    leitfaden_kek = db.Column(db.String(10), default="k.A.", nullable=True)
    leitfaden_angebot = db.Column(db.String(10), default="k.A.", nullable=True)
    leitfaden_zusammenfassung = db.Column(db.String(10), default="k.A.", nullable=True)
    leitfaden_kzb = db.Column(db.String(10), default="k.A.", nullable=True)
    
    performance_mark = db.Column(db.Integer, nullable=True) 
    time_spent = db.Column(db.Integer, nullable=True) 
    project_leader_notes = db.Column(db.Text, nullable=True)
    
    @property
    def leitfaden_erfuellung_display(self): 
        leitfaden_fields = [
            self.leitfaden_begruessung, self.leitfaden_legitimation, self.leitfaden_pka,
            self.leitfaden_kek, self.leitfaden_angebot, self.leitfaden_zusammenfassung, self.leitfaden_kzb
        ]
        ja_count = sum(1 for x in leitfaden_fields if x == "Ja")
        total_relevant_fields = sum(1 for x in leitfaden_fields if x != "k.A.")
        
        if total_relevant_fields == 0:
            return "N/A" 
        return f"{ja_count}/{total_relevant_fields}"

    @property
    def overall_score(self): # KORRIGIERTE VERSION - NUR EINE DEFINITION
        if self.performance_mark is None:
            return 0.0 
        performance_percentage = (float(self.performance_mark) / 10.0) * 100.0
        return round(performance_percentage, 2)

    # Die zweite, fehlerhafte overall_score Definition wurde ENTFERNT.
    # Die leitfaden_score_details Property wurde bereits zu leitfaden_erfuellung_display umbenannt.

    def __repr__(self):
        return f'<Coaching {self.id} for TeamMember {self.team_member_id} on {self.coaching_date}>'

print("<<<< ENDE models.py (KORRIGIERTE VERSION) GELADEN >>>>")
