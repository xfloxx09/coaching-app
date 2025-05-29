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

class RegistrationForm(FlaskForm): # Wird für die Admin User Erstellung verwendet
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
        # Baue Choices für Team-Auswahl
        team_choices = [(0, 'Kein Team (für Nicht-Teamleiter)')] # Standard-Option
        if active_teams:
            team_choices.extend([(t.id, t.name) for t in active_teams])
        else: # Wenn keine Teams da sind, aber die "Kein Team"-Option nicht die einzige sein soll für die Logik unten
            if len(team_choices) == 1 and team_choices[0][0] == 0: # Nur die "Kein Team" Option ist da
                 team_choices.append(("", 'Zuerst Teams erstellen')) # Füge einen Platzhalter hinzu
                 # Alternativ könnte man das Feld deaktivieren oder eine andere Logik verwenden

        self.team_id.choices = team_choices


    def validate_username(self, username_field):
        query = User.query.filter(User.username == username_field.data)
        if self.original_username and self.original_username == username_field.data:
            return # Beim Bearbeiten ist der eigene aktuelle Username okay
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
            # Wenn keine Teams da sind, ist es schwierig, ein Mitglied zu erstellen.
            # DataRequired wird hier fehlschlagen.
            self.team_id.choices = [("", "Bitte zuerst Teams erstellen")]


LEITFADEN_CHOICES = [('Ja', 'Ja'), ('Nein', 'Nein'), ('k.A.', 'k.A.')]
COACHING_SUBJECT_CHOICES = [
    ('', '--- Bitte wählen ---'), 
    ('Sales', 'Sales'),
    ('Qualität', 'Qualität'),
    ('Allgemein', 'Allgemein') 
]

class CoachingForm(FlaskForm):
    # coerce=int bleibt, da die IDs der Mitglieder Integer sind.
    team_member_id = SelectField(
        'Teammitglied', 
        coerce=int, 
        validators=[DataRequired("Teammitglied ist erforderlich.")], 
        option_widget=None, 
        # choices werden im __init__ dynamisch gesetzt
    )
    # ... (Rest der Felder wie coaching_style, coaching_subject etc. bleiben gleich) ...
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
        
        generated_choices = [] # Liste für (value, label) Tupel

        if current_user_role == 'Teamleiter' and current_user_team_id:
            team_members = TeamMember.query.filter_by(team_id=current_user_team_id).order_by(TeamMember.name).all()
            if team_members:
                for m in team_members:
                    generated_choices.append((m.id, m.name))
            # Wenn keine Mitglieder, bleibt generated_choices leer
        
        else: # Für Nicht-Teamleiter (QM, SalesCoach, Trainer, Admin)
            all_teams = Team.query.order_by(Team.name).all()
            if all_teams:
                for team_obj in all_teams:
                    members = TeamMember.query.filter_by(team_id=team_obj.id).order_by(TeamMember.name).all()
                    if members:
                        for m in members:
                            generated_choices.append((m.id, f"{m.name} ({team_obj.name})"))
            # Wenn keine Teams oder keine Mitglieder, bleibt generated_choices leer
        
        # Setze die Choices für das Feld
        if not generated_choices:
            # Wenn keine validen Mitglieder gefunden wurden, ist es schwierig, DataRequired zu erfüllen.
            # Eine Option ist, eine nicht-wählbare "Keine Mitglieder"-Option anzubieten,
            # aber das löst das DataRequired-Problem nicht, wenn es die einzige Option ist.
            # Besser ist es, das Formular gar nicht erst zu validieren, wenn keine Auswahl möglich ist,
            # oder eine entsprechende Meldung anzuzeigen.
            # Für den Moment setzen wir eine leere Choice, die DataRequired fehlschlagen lässt.
            self.team_member_id.choices = [("", "Keine auswählbaren Mitglieder")]
            # Und vielleicht eine Meldung in der Route flashen, dass keine Mitglieder da sind.
        else:
            # Füge eine "Bitte wählen"-Option hinzu, WENN das Feld Pflicht ist (DataRequired)
            # UND wenn die Liste nicht leer ist UND die erste Option nicht schon ein Platzhalter ist.
            has_data_required = any(isinstance(v, DataRequired) for v in self.team_member_id.validators)
            if has_data_required and (not generated_choices or generated_choices[0][0] != ""):
                 self.team_member_id.choices = [("", "--- Bitte wählen ---")] + generated_choices
            else:
                 self.team_member_id.choices = generated_choices
        
        print(f"DEBUG CoachingForm Init Final Choices: {self.team_member_id.choices[:5]}") # DEBUG


class ProjectLeaderNoteForm(FlaskForm):
    # coaching_id wurde hier entfernt, da es manuell im Template als <input type="hidden"> gesendet wird.
    # Das Formular ist jetzt primär für 'notes' und das CSRF-Token zuständig (das WTForms automatisch handhabt).
    notes = TextAreaField('PL/QM Notiz', # Label angepasst
                          validators=[DataRequired("Die Notiz darf nicht leer sein."), 
                                      Length(max=2000)])
    # Submit-Button wird im HTML definiert, daher hier nicht als Feld nötig
    # submit = SubmitField('Notiz speichern') 
