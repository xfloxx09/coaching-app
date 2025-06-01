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
        ('Qualitätsmanager', 'Qualitäts-Coach'),
        ('SalesCoach', 'Sales-Coach'),
        ('Trainer', 'Trainer'),
        ('Projektleiter', 'AL/PL'),
        ('Admin', 'Admin'),
        ('Abteilungsleiter', 'Abteilungsleiter'),
        ('Team_Manager', 'Team-Manager')
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
        possible_leaders = User.query.filter(User.role.in_(['Teamleiter', 'Admin', ''])).order_by(User.username).all()
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
        coerce=int, # Wir lassen coerce=int hier, da wir Integer-IDs erwarten
        validators=[DataRequired("Teammitglied ist erforderlich.")], 
        option_widget=None
        # choices werden im __init__ dynamisch gesetzt
    )
    # ... (Rest der Felder wie coaching_style, coaching_subject etc. bleiben gleich) ...
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

    def __init__(self, current_user_role=None, current_user_team_id=None, *args, **kwargs):
        super(CoachingForm, self).__init__(*args, **kwargs)
        
        generated_choices = [] 

        if current_user_role == 'Teamleiter' and current_user_team_id:
            team_members = TeamMember.query.filter_by(team_id=current_user_team_id).order_by(TeamMember.name).all()
            for m in team_members:
                generated_choices.append((m.id, m.name)) # Wert ist m.id (Integer)
        else: 
            all_teams = Team.query.order_by(Team.name).all()
            for team_obj in all_teams:
                members = TeamMember.query.filter_by(team_id=team_obj.id).order_by(TeamMember.name).all()
                for m in members:
                    generated_choices.append((m.id, f"{m.name} ({team_obj.name})")) # Wert ist m.id (Integer)
        
        # Setze die Choices für das Feld
        # Wichtig: Wenn generated_choices leer ist, wird DataRequired später bei der Validierung fehlschlagen,
        # was korrekt ist. Wir fügen KEINE Platzhalter-Optionen mit leerem String als Wert hinzu,
        # wenn coerce=int ist, da dies den ValueError beim Rendern verursacht.
        if not generated_choices:
            # Wenn keine Mitglieder da sind, bleibt die Choice-Liste leer.
            # Das Template muss ggf. darauf reagieren oder eine Meldung anzeigen.
            # WTForms wird das leere Select-Feld rendern.
            self.team_member_id.choices = [] 
            print(f"DEBUG CoachingForm Init: Keine Mitglieder gefunden, Choices sind leer.")
        else:
            # Wenn Mitglieder vorhanden sind, füge eine "Bitte wählen"-Option hinzu,
            # aber mit einem nicht-numerischen oder ungültigen Wert, der coerce=int nicht stört,
            # und den DataRequired-Validator fehlschlagen lässt, wenn er ausgewählt bleibt.
            # Besser ist, das Feld initial leer zu lassen, wenn möglich, und auf die Validierung zu vertrauen.
            # Für die Auswahl:
            # Die "Bitte wählen"-Option sollte idealerweise einen Wert haben, der nicht mit echten IDs kollidiert
            # und vom coerce-Typ nicht erfasst wird, wenn er nicht None ist.
            # Da wir coerce=int haben, DARF der Wert für "Bitte wählen" KEIN leerer String sein.
            # Wir lassen "Bitte wählen" hier weg und verlassen uns auf DataRequired.
            # Wenn du eine "Bitte wählen"-Option visuell möchtest, die nicht validiert,
            # müsste sie einen nicht-Integer-Wert haben und das Feld dürfte nicht DataRequired sein,
            # oder die Validierung müsste komplexer werden.

            # Einfachste Lösung: Nur die gültigen Choices setzen.
            self.team_member_id.choices = generated_choices
            print(f"DEBUG CoachingForm Init Final Choices: {self.team_member_id.choices[:5]}")


class ProjectLeaderNoteForm(FlaskForm):
    notes = TextAreaField('PL/QM Notiz', 
                          validators=[DataRequired("Die Notiz darf nicht leer sein."), 
                                      Length(max=2000)])
    # coaching_id und submit werden im Template/Route gehandhabt
