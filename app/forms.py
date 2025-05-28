from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, IntegerField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Length, NumberRange
from app.models import User, Team, TeamMember

class LoginForm(FlaskForm):
    username = StringField('Benutzername', validators=[DataRequired("Benutzername ist erforderlich.")])
    password = PasswordField('Passwort', validators=[DataRequired("Passwort ist erforderlich.")])
    remember_me = BooleanField('Angemeldet bleiben')
    submit = SubmitField('Anmelden')

class RegistrationForm(FlaskForm): # Für Admin User Erstellung
    username = StringField('Benutzername', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('E-Mail', validators=[DataRequired(), Email()])
    password = PasswordField('Passwort', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField(
        'Passwort wiederholen', validators=[DataRequired(), EqualTo('password', message='Passwörter müssen übereinstimmen.')])
    role = SelectField('Rolle', choices=[
        ('Teammitglied', 'Teammitglied (Standard)'), # Sollte eigentlich nicht manuell gesetzt werden, sondern durch Zuweisung zu Team
        ('Teamleiter', 'Teamleiter'),
        ('Qualitätsmanager', 'Qualitätsmanager'),
        ('SalesCoach', 'Sales Coach'),
        ('Trainer', 'Trainer'),
        ('Projektleiter', 'Projektleiter'),
        ('Admin', 'Admin')
    ], validators=[DataRequired()])
    team_id = SelectField('Team (nur für Teamleiter)', coerce=int, validators=[], option_widget=None, choices=[]) # Choices werden dynamisch geladen
    submit = SubmitField('Benutzer registrieren')

    def __init__(self, *args, **kwargs):
        super(RegistrationForm, self).__init__(*args, **kwargs)
        self.team_id.choices = [(t.id, t.name) for t in Team.query.order_by(Team.name).all()]
        self.team_id.choices.insert(0, (0, 'Kein Team (für Nicht-Teamleiter)')) # Option für kein Team

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Dieser Benutzername ist bereits vergeben.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Diese E-Mail-Adresse ist bereits registriert.')

class TeamForm(FlaskForm):
    name = StringField('Team Name', validators=[DataRequired(), Length(min=3, max=100)])
    team_leader_id = SelectField('Teamleiter', coerce=int, option_widget=None, choices=[])
    submit = SubmitField('Team erstellen/aktualisieren')

    def __init__(self, *args, **kwargs):
        super(TeamForm, self).__init__(*args, **kwargs)
        # Lade nur User, die die Rolle Teamleiter haben oder keine Rolle (impliziert potentieller TL)
        # oder Admin/Projektleiter die auch als TL agieren könnten (flexibel halten)
        possible_leaders = User.query.filter(User.role.in_(['Teamleiter', 'Admin', 'Projektleiter'])).order_by(User.username).all()
        self.team_leader_id.choices = [(u.id, u.username) for u in possible_leaders]
        self.team_leader_id.choices.insert(0, (0, 'Kein Teamleiter ausgewählt'))


class TeamMemberForm(FlaskForm):
    name = StringField('Name des Teammitglieds', validators=[DataRequired(), Length(min=2, max=100)])
    team_id = SelectField('Team', coerce=int, validators=[DataRequired()], option_widget=None, choices=[])
    submit = SubmitField('Teammitglied erstellen/aktualisieren')

    def __init__(self, *args, **kwargs):
        super(TeamMemberForm, self).__init__(*args, **kwargs)
        self.team_id.choices = [(t.id, t.name) for t in Team.query.order_by(Team.name).all()]
        if not self.team_id.choices: # Fallback, falls keine Teams existieren
            self.team_id.choices = [(0, "Bitte zuerst Teams erstellen")]


LEITFADEN_CHOICES = [('Ja', 'Ja'), ('Nein', 'Nein'), ('k.A.', 'k.A.')]

class CoachingForm(FlaskForm):
    team_member_id = SelectField('Teammitglied', coerce=int, validators=[DataRequired()], option_widget=None, choices=[])
    coaching_style = SelectField('Coaching Stil', choices=[
        ('Side-by-Side', 'Side-by-Side'),
        ('TCAP', 'TCAP')
    ], validators=[DataRequired()])
    tcap_id = StringField('T-CAP ID (falls TCAP gewählt)') # Validierung könnte man mit JS dynamisch machen
    
    leitfaden_begruessung = SelectField('Begrüßung', choices=LEITFADEN_CHOICES, default='k.A.')
    leitfaden_legitimation = SelectField('Legitimation', choices=LEITFADEN_CHOICES, default='k.A.')
    leitfaden_pka = SelectField('PKA', choices=LEITFADEN_CHOICES, default='k.A.')
    leitfaden_kek = SelectField('KEK', choices=LEITFADEN_CHOICES, default='k.A.')
    leitfaden_angebot = SelectField('Angebot', choices=LEITFADEN_CHOICES, default='k.A.')
    leitfaden_zusammenfassung = SelectField('Zusammenfassung', choices=LEITFADEN_CHOICES, default='k.A.')
    leitfaden_kzb = SelectField('KZB', choices=LEITFADEN_CHOICES, default='k.A.')
    
    performance_mark = IntegerField('Performance Note (0-10)', validators=[DataRequired(), NumberRange(min=0, max=10)])
    time_spent = IntegerField('Zeitaufwand (Minuten)', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Coaching speichern')

    def __init__(self, current_user_role=None, current_user_team_id=None, *args, **kwargs):
        super(CoachingForm, self).__init__(*args, **kwargs)
        if current_user_role == 'Teamleiter' and current_user_team_id:
            # Teamleiter sieht nur Mitglieder seines Teams
            team_members = TeamMember.query.filter_by(team_id=current_user_team_id).order_by(TeamMember.name).all()
        else:
            # Andere Rollen sehen alle Mitglieder, gruppiert nach Team
            all_teams = Team.query.order_by(Team.name).all()
            team_members_choices = []
            for team in all_teams:
                members = TeamMember.query.filter_by(team_id=team.id).order_by(TeamMember.name).all()
                if members:
                    team_members_choices.append( (f'Team: {team.name}', [(m.id, m.name) for m in members]) ) # Optgroup
            if team_members_choices:
                 self.team_member_id.choices = team_members_choices
            else: # Fallback
                self.team_member_id.choices = [(0, "Keine Teammitglieder gefunden")]
            return # Wichtig, damit die untere Zuweisung nicht auch noch greift

        # Normale Zuweisung für Teamleiter
        if team_members:
            self.team_member_id.choices = [(m.id, m.name) for m in team_members]
        else:
            self.team_member_id.choices = [(0, "Keine Mitglieder in Ihrem Team")]


class ProjectLeaderNoteForm(FlaskForm):
    coaching_id = HiddenField() # Unsichtbares Feld um Coaching ID zu übermitteln
    notes = TextAreaField('Notizen des Projektleiters', validators=[DataRequired(), Length(max=2000)])
    submit = SubmitField('Notiz speichern')