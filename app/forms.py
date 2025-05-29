# app/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, IntegerField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, EqualTo, ValidationError, Length, NumberRange 
from app.models import User, Team, TeamMember # Stelle sicher, dass alle Modelle importiert sind

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
        team_choices = [(0, 'Kein Team (für Nicht-Teamleiter)')] 
        if active_teams:
            team_choices.extend([(t.id, t.name) for t in active_teams])
        elif len(team_choices) == 1 and team_choices[0][0] == 0:
             team_choices.append(("", 'Zuerst Teams erstellen'))
        self.team_id.choices = team_choices

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
    team_id = SelectField('Team', coerce=int, validators=[DataRequired("Team ist erforderlich.")], option_widget=None, choices=[])
    submit = SubmitField('Teammitglied erstellen/aktualisieren')

    def __init__(self, *args, **kwargs):
        super(TeamMemberForm, self).__init__(*args, **kwargs)
        active_teams = Team.query.order_by(Team.name).all()
        if active_teams:
            self.team_id.choices = [(t.id, t.name) for t in active_teams]
        else:
            self.team_id.choices = [("", "Bitte zuerst Teams erstellen")] # Wert ist leerer String

LEITFADEN_CHOICES = [('Ja', 'Ja'), ('Nein', 'Nein'), ('k.A.', 'k.A.')]
COACHING_SUBJECT_CHOICES = [
    ('', '--- Bitte wählen ---'), 
    ('Sales', 'Sales'),
    ('Qualität', 'Qualität'),
    ('Allgemein', 'Allgemein') 
]

class CoachingForm(FlaskForm):
    team_member_id = SelectField(
        'Teammitglied', 
        # coerce wird dynamisch im __init__ gesetzt
        validators=[DataRequired("Teammitglied ist erforderlich.")], 
        option_widget=None
    )
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
        
        generated_choices = [] 

        if current_user_role == 'Teamleiter' and current_user_team_id:
            team_members = TeamMember.query.filter_by(team_id=current_user_team_id).order_by(TeamMember.name).all()
            for m in team_members:
                generated_choices.append((m.id, m.name))
        else: 
            all_teams = Team.query.order_by(Team.name).all()
            for team_obj in all_teams:
                members = TeamMember.query.filter_by(team_id=team_obj.id).order_by(TeamMember.name).all()
                for m in members:
                    generated_choices.append((m.id, f"{m.name} ({team_obj.name})"))
        
        has_data_required = any(isinstance(v, DataRequired) for v in self.team_member_id.validators)

        if not generated_choices:
            self.team_member_id.choices = [("", "Keine Mitglieder verfügbar")]
            self.team_member_id.coerce = str # Wichtig, um ValueError beim Rendern zu vermeiden
        else:
            self.team_member_id.coerce = int # Standard coerce für gültige IDs
            if has_data_required:
                 # Füge "Bitte wählen" nur hinzu, wenn es tatsächliche Optionen gibt
                 self.team_member_id.choices = [("", "--- Bitte wählen ---")] + generated_choices
            else:
                 self.team_member_id.choices = generated_choices
        
        print(f"DEBUG CoachingForm Init Final Choices: {self.team_member_id.choices[:5]}, Coerce: {self.team_member_id.coerce}")


class ProjectLeaderNoteForm(FlaskForm):
    notes = TextAreaField('PL/QM Notiz', 
                          validators=[DataRequired("Die Notiz darf nicht leer sein."), 
                                      Length(max=2000)])
    # coaching_id und submit werden im Template/Route gehandhabt
