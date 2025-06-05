# app/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, IntegerField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, EqualTo, ValidationError, Length, NumberRange 
# <<< GEÄNDERT >>> Importiere die ARCHIV-Konstante
from app.models import User, Team, TeamMember
from app.utils import ARCHIV_TEAM_NAME

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
        ('Qualitätsmanager', 'Qualitäts-Coach'),
        ('SalesCoach', 'Sales-Coach'),
        ('Trainer', 'Trainer'),
        ('Projektleiter', 'AL/PL'),
        ('Admin', 'Admin'),
        ('Abteilungsleiter', 'Abteilungsleiter')
    ], validators=[DataRequired("Rolle ist erforderlich.")])
    team_id = SelectField('Team (nur für Teamleiter)', coerce=int, option_widget=None, choices=[])
    submit = SubmitField('Benutzer registrieren/aktualisieren')

    def __init__(self, original_username=None, *args, **kwargs):
        super(RegistrationForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        # <<< GEÄNDERT >>> Schließt das ARCHIV-Team aus der Auswahl aus
        active_teams = Team.query.filter(Team.name != ARCHIV_TEAM_NAME).order_by(Team.name).all()
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

    def __init__(self, original_name=None, *args, **kwargs): # original_name für Validierung hinzugefügt
        super(TeamForm, self).__init__(*args, **kwargs)
        self.original_name = original_name
        possible_leaders = User.query.filter(User.role.in_(['Teamleiter', 'Admin', ''])).order_by(User.username).all()
        self.team_leader_id.choices = [(u.id, u.username) for u in possible_leaders]
        self.team_leader_id.choices.insert(0, (0, 'Kein Teamleiter ausgewählt'))
    
    # <<< NEU >>> Validierung, um Konflikte mit ARCHIV zu vermeiden
    def validate_name(self, name_field):
        # Wenn der Name nicht geändert wurde, überspringe die Prüfung
        if self.original_name and self.original_name.strip().upper() == name_field.data.strip().upper():
            return
        # Prüfe auf Duplikate
        if Team.query.filter(Team.name.ilike(name_field.data)).first():
            raise ValidationError('Ein Team mit diesem Namen existiert bereits.')
        # Prüfe auf reservierten Namen
        if name_field.data.strip().upper() == ARCHIV_TEAM_NAME:
            raise ValidationError(f'Der Teamname "{ARCHIV_TEAM_NAME}" ist für das System reserviert.')


class TeamMemberForm(FlaskForm):
    name = StringField('Name des Teammitglieds', validators=[DataRequired(), Length(min=2, max=100)])
    team_id = SelectField('Team', coerce=int, validators=[DataRequired("Team ist erforderlich.")], option_widget=None, choices=[])
    submit = SubmitField('Teammitglied erstellen/aktualisieren')

    def __init__(self, *args, **kwargs):
        super(TeamMemberForm, self).__init__(*args, **kwargs)
        # <<< GEÄNDERT >>> Schließt das ARCHIV-Team aus der Auswahl aus
        active_teams = Team.query.filter(Team.name != ARCHIV_TEAM_NAME).order_by(Team.name).all()
        if active_teams:
            self.team_id.choices = [(t.id, t.name) for t in active_teams]
        else:
            self.team_id.choices = [("", "Bitte zuerst Teams erstellen")]

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
        coerce=int,
        validators=[DataRequired("Teammitglied ist erforderlich.")], 
        option_widget=None
    )
    coaching_style = SelectField('Coaching Stil', choices=[('Side-by-Side', 'Side-by-Side'), ('TCAP', 'TCAP')], validators=[DataRequired("Coaching-Stil ist erforderlich.")])
    tcap_id = StringField('T-CAP ID (falls TCAP gewählt)')
    coaching_subject = SelectField('Coaching Thema', choices=COACHING_SUBJECT_CHOICES, validators=[DataRequired("Coaching-Thema ist erforderlich.")])
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

    # <<< GEÄNDERT >>> Der __init__ wird vereinfacht.
    # Er speichert nur noch die Benutzerinformationen. Die Logik zum Füllen der Choices wird ausgelagert.
    def __init__(self, current_user_role=None, current_user_team_id=None, *args, **kwargs):
        super(CoachingForm, self).__init__(*args, **kwargs)
        self.current_user_role = current_user_role
        self.current_user_team_id = current_user_team_id

    # <<< NEU >>> Die Methode, die in der Route aufgerufen wird, um die Choices zu füllen.
    def update_team_member_choices(self, exclude_archiv=False):
        """
        Füllt dynamisch die Auswahl für team_member_id, basierend auf der Rolle des Benutzers
        und ob das Archiv ausgeschlossen werden soll.
        """
        generated_choices = [] 

        if self.current_user_role == 'Teamleiter' and self.current_user_team_id:
            # Teamleiter sehen nur Mitglieder ihres eigenen Teams.
            team_members = TeamMember.query.filter_by(team_id=self.current_user_team_id).order_by(TeamMember.name).all()
            for m in team_members:
                generated_choices.append((m.id, m.name))
        else: 
            # Admins, QM, etc. sehen Mitglieder aus allen Teams.
            query = Team.query
            if exclude_archiv:
                # Schließt das ARCHIV-Team aus, wenn angefordert (z.B. beim Hinzufügen eines neuen Coachings).
                query = query.filter(Team.name != ARCHIV_TEAM_NAME)
            
            all_teams_for_choices = query.order_by(Team.name).all()
            for team_obj in all_teams_for_choices:
                members = TeamMember.query.filter_by(team_id=team_obj.id).order_by(TeamMember.name).all()
                for m in members:
                    generated_choices.append((m.id, f"{m.name} ({team_obj.name})"))
        
        # Setzt die Choices. Wenn keine Mitglieder gefunden werden, ist die Liste leer,
        # was den DataRequired-Validator korrekt fehlschlagen lässt.
        self.team_member_id.choices = generated_choices


class ProjectLeaderNoteForm(FlaskForm):
    notes = TextAreaField('PL/QM Notiz', 
                          validators=[DataRequired("Die Notiz darf nicht leer sein."), 
                                      Length(max=2000)])
    # coaching_id und submit werden im Template/Route gehandhabt
