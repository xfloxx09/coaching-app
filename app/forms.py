# app/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, IntegerField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, EqualTo, ValidationError, Length, NumberRange 
from app.models import User, Team, TeamMember

class LoginForm(FlaskForm):
    username = StringField('Benutzername', validators=[DataRequired("Benutzername ist erforderlich.")])
    password = PasswordField('Passwort', validators=[DataRequired("Passwort ist erforderlich.")])
    remember_me = BooleanField('Angemeldet bleiben')
    submit = SubmitField('Anmelden')

class RegistrationForm(FlaskForm):
    username = StringField('Benutzername', validators=[DataRequired("Benutzername ist erforderlich."), Length(min=3, max=64)])
    email = StringField('E-Mail (Optional)') 
    password = PasswordField('Passwort', validators=[DataRequired("Passwort ist erforderlich."), Length(min=6)])
    password2 = PasswordField(
        'Passwort wiederholen', 
        validators=[DataRequired("Passwortwiederholung ist erforderlich."), EqualTo('password', message='Passwörter müssen übereinstimmen.')]
    )
    role = SelectField('Rolle', choices=[
        ('Teamleiter', 'Teamleiter'),
        ('Qualitätsmanager', 'Qualitätsmanager'),
        ('SalesCoach', 'Sales Coach'),
        ('Trainer', 'Trainer'),
        ('Projektleiter', 'Projektleiter'),
        ('Admin', 'Admin')
    ], validators=[DataRequired("Rolle ist erforderlich.")])
    team_id = SelectField('Team (nur für Teamleiter)', coerce=int, option_widget=None, choices=[])
    submit = SubmitField('Benutzer registrieren/aktualisieren')

    def __init__(self, original_username=None, *args, **kwargs):
        super(RegistrationForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        active_teams = Team.query.order_by(Team.name).all()
        self.team_id.choices = [(t.id, t.name) for t in active_teams]
        self.team_id.choices.insert(0, (0, 'Kein Team (für Nicht-Teamleiter)'))
        if not active_teams and len(self.team_id.choices) == 1:
             self.team_id.choices = [(0, 'Zuerst Teams erstellen')]

    def validate_username(self, username_field):
        query = User.query.filter(User.username == username_field.data)
        if self.original_username and self.original_username == username_field.data:
            return
        user = query.first()
        if user:
            raise ValidationError('Dieser Benutzername ist bereits vergeben.')

class TeamForm(FlaskForm):
    name = StringField('Team Name', validators=[DataRequired(), Length(min=3, max=100)])
    team_leader_id = SelectField('Teamleiter', coerce=int, option_widget=None, choices=[])
    submit = SubmitField('Team erstellen/aktualisieren')

    def __init__(self, *args, **kwargs):
        super(TeamForm, self).__init__(*args, **kwargs)
        possible_leaders = User.query.filter(User.role.in_(['Teamleiter', 'Admin', 'Projektleiter'])).order_by(User.username).all()
        self.team_leader_id.choices = [(u.id, u.username) for u in possible_leaders]
        self.team_leader_id.choices.insert(0, (0, 'Kein Teamleiter ausgewählt'))

class TeamMemberForm(FlaskForm):
    name = StringField('Name des Teammitglieds', validators=[DataRequired(), Length(min=2, max=100)])
    team_id = SelectField('Team', coerce=int, validators=[DataRequired()], option_widget=None, choices=[])
    submit = SubmitField('Teammitglied erstellen/aktualisieren')

    def __init__(self, *args, **kwargs):
        super(TeamMemberForm, self).__init__(*args, **kwargs)
        active_teams = Team.query.order_by(Team.name).all()
        self.team_id.choices = [(t.id, t.name) for t in active_teams]
        if not active_teams:
            self.team_id.choices = [(0, "Bitte zuerst Teams erstellen")]

LEITFADEN_CHOICES = [('Ja', 'Ja'), ('Nein', 'Nein'), ('k.A.', 'k.A.')]
COACHING_SUBJECT_CHOICES = [
    ('', '--- Bitte wählen ---'),
    ('Sales', 'Sales'),
    ('Qualität', 'Qualität'),
    ('Allgemein', 'Allgemein') 
]

class CoachingForm(FlaskForm):
    team_member_id = SelectField('Teammitglied', coerce=int, validators=[DataRequired("Teammitglied ist erforderlich.")], option_widget=None, choices=[])
    coaching_style = SelectField('Coaching Stil', choices=[
        ('Side-by-Side', 'Side-by-Side'),
        ('TCAP', 'TCAP')
    ], validators=[DataRequired("Coaching-Stil ist erforderlich.")])
    tcap_id = StringField('T-CAP ID (falls TCAP gewählt)')
    coaching_subject = SelectField('Coaching Betreff', choices=COACHING_SUBJECT_CHOICES, validators=[DataRequired("Betreff ist erforderlich.")])
    leitfaden_begruessung = SelectField('Begrüßung', choices=LEITFADEN_CHOICES, default='k.A.')
    leitfaden_legitimation = SelectField('Legitimation', choices=LEITFADEN_CHOICES, default='k.A.')
    leitfaden_pka = SelectField('PKA', choices=LEITFADEN_CHOICES, default='k.A.')
    leitfaden_kek = SelectField('KEK', choices=LEITFADEN_CHOICES, default='k.A.')
    leitfaden_angebot = SelectField('Angebot', choices=LEITFADEN_CHOICES, default='k.A.')
    leitfaden_zusammenfassung = SelectField('Zusammenfassung', choices=LEITFADEN_CHOICES, default='k.A.')
    leitfaden_kzb = SelectField('KZB', choices=LEITFADEN_CHOICES, default='k.A.')
    performance_mark = IntegerField('Performance Note (0-10)', validators=[DataRequired("Performance Note ist erforderlich."), NumberRange(min=0, max=10)])
    time_spent = IntegerField('Zeitaufwand (Minuten)', validators=[DataRequired("Zeitaufwand ist erforderlich."), NumberRange(min=1)])
    coach_notes = TextAreaField('Notizen des Coaches', validators=[Length(max=2000)])
    submit = SubmitField('Coaching speichern')

    def __init__(self, current_user_role=None, current_user_team_id=None, *args, **kwargs):
        super(CoachingForm, self).__init__(*args, **kwargs)
        if current_user_role == 'Teamleiter' and current_user_team_id:
            team_members = TeamMember.query.filter_by(team_id=current_user_team_id).order_by(TeamMember.name).all()
            if team_members:
                self.team_member_id.choices = [(m.id, m.name) for m in team_members]
            else:
                self.team_member_id.choices = [(0, "Keine Mitglieder in Ihrem Team")]
        else:
            all_teams = Team.query.order_by(Team.name).all()
            team_members_choices = []
            for team_val in all_teams:
                members = TeamMember.query.filter_by(team_id=team_val.id).order_by(TeamMember.name).all()
                if members:
                    team_members_choices.append( (f'Team: {team_val.name}', [(m.id, m.name) for m in members]) )
            if team_members_choices:
                 self.team_member_id.choices = team_members_choices
            else:
                self.team_member_id.choices = [(0, "Keine Teammitglieder gefunden")]

class ProjectLeaderNoteForm(FlaskForm):
    # coaching_id ist nicht mehr hier, da es manuell im Template als <input type="hidden"> gesendet wird.
    # Das Formular ist jetzt nur für 'notes' und das CSRF-Token zuständig.
    notes = TextAreaField('Notizen des Projektleiters', 
                          validators=[DataRequired("Die Notiz darf nicht leer sein."), 
                                      Length(max=2000)])
    # submit = SubmitField('Notiz speichern') # Der Submit-Button wird im HTML definiert
