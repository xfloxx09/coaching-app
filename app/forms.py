# app/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, IntegerField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, EqualTo, ValidationError, Length, NumberRange, Optional # Added Optional
from app.models import User, Team, TeamMember, Coaching # Coaching not strictly needed here but good for consistency
from app.utils import ROLE_TEAMLEITER, ROLE_ADMIN, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_TEAMMITGLIED, ROLE_PROJEKTLEITER, ROLE_ABTEILUNGSLEITER # Ensure all roles are imported
from sqlalchemy import func # For case-insensitive username check

class LoginForm(FlaskForm):
    username = StringField('Benutzername', validators=[DataRequired("Benutzername ist erforderlich.")])
    password = PasswordField('Passwort', validators=[DataRequired("Passwort ist erforderlich.")])
    remember_me = BooleanField('Angemeldet bleiben')
    submit = SubmitField('Anmelden')

class RegistrationForm(FlaskForm): 
    username = StringField('Benutzername', validators=[DataRequired("Benutzername ist erforderlich."), Length(min=3, max=64)])
    email = StringField('E-Mail (Optional)', validators=[Optional(), Length(max=120)])
    password = PasswordField('Passwort', validators=[DataRequired("Passwort ist erforderlich."), Length(min=6)])
    password2 = PasswordField(
        'Passwort wiederholen', 
        validators=[DataRequired("Passwortwiederholung ist erforderlich."), EqualTo('password', message='Passwörter müssen übereinstimmen.')]
    )
    # Using constants for role choices if they are defined in utils.py
    # Otherwise, keep original string literals.
    role_choices = [
        (ROLE_TEAMLEITER, 'Teamleiter'), (ROLE_QM, 'Qualitäts-Coach'), (ROLE_SALESCOACH, 'Sales-Coach'),
        (ROLE_TRAINER, 'Trainer'), (ROLE_PROJEKTLEITER, 'AL/PL'), (ROLE_ADMIN, 'Admin'), 
        (ROLE_ABTEILUNGSLEITER, 'Abteilungsleiter')
    ]
    # Add Teammitglied if it's a selectable role during registration
    if hasattr(ROLE_TEAMMITGLIED, '__isidentifier__'): # Check if constant exists
         role_choices.append((ROLE_TEAMMITGLIED, 'Teammitglied (App User)'))
    else: # Fallback if ROLE_TEAMMITGLIED is not defined as expected
         role_choices.append(('Teammitglied', 'Teammitglied (App User)'))


    role = SelectField('Rolle', choices=role_choices, validators=[DataRequired("Rolle ist erforderlich.")])
    
    # Renamed from 'team_id' to 'team_id_for_leader' to avoid conflict if this form ever manages general team_id
    team_id_for_leader = SelectField('Team (nur für Rolle Teamleiter)', coerce=int, validators=[Optional()]) 
    submit = SubmitField('Benutzer registrieren/aktualisieren')

    def __init__(self, original_username=None, *args, **kwargs):
        super(RegistrationForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        
        # Populate team_id_for_leader choices
        all_teams = Team.query.order_by(Team.name).all() # Changed to all_teams for consistency
        leader_team_choices = [(0, 'Kein Team (Standard für Nicht-Teamleiter)')] 
        if all_teams:
            leader_team_choices.extend([(t.id, t.name) for t in all_teams])
        else: # If no teams exist, add a placeholder to inform admin
             leader_team_choices.append(("", 'Zuerst Teams erstellen'))
        self.team_id_for_leader.choices = leader_team_choices

    def validate_username(self, username_field):
        # Case-insensitive check for username uniqueness
        if self.original_username and self.original_username.lower() == username_field.data.lower():
            return # Original username is fine
        
        user = User.query.filter(func.lower(User.username) == func.lower(username_field.data)).first()
        if user:
            raise ValidationError('Dieser Benutzername ist bereits vergeben. Bitte wählen Sie einen anderen.')

class TeamForm(FlaskForm):
    name = StringField('Team Name', validators=[DataRequired(), Length(min=3, max=100)])
    team_leader_id = SelectField('Teamleiter', coerce=int, validators=[Optional()])
    submit = SubmitField('Team erstellen/aktualisieren')

    def __init__(self, *args, **kwargs):
        super(TeamForm, self).__init__(*args, **kwargs)
        # Assuming only users with 'Teamleiter' role can be assigned as team leaders directly here.
        # Admins can also be leaders, but might be set via User edit.
        possible_leaders = User.query.filter(User.role == ROLE_TEAMLEITER).order_by(User.username).all()
        self.team_leader_id.choices = [(u.id, u.username) for u in possible_leaders]
        self.team_leader_id.choices.insert(0, (0, 'Kein Teamleiter ausgewählt'))

class TeamMemberForm(FlaskForm):
    name = StringField('Name des Teammitglieds', validators=[DataRequired(), Length(min=2, max=100)])
    # coerce=int means the form data will be an integer. '0' is a valid int.
    # validators=[Optional()] means the field can be empty or not present, but if present, coerce=int applies.
    team_id = SelectField('Aktuelle Team Zugehörigkeit', coerce=int, validators=[Optional()]) 
    submit = SubmitField('Teammitglied speichern')

    def __init__(self, *args, **kwargs):
        super(TeamMemberForm, self).__init__(*args, **kwargs)
        all_teams = Team.query.order_by(Team.name).all()
        # Value '0' will signify "No Team" / "Archived". This is handled in the route.
        team_choices = [(0, 'Kein Team (Mitglied wird archiviert/unzugewiesen)')] 
        if all_teams:
            team_choices.extend([(t.id, t.name) for t in all_teams])
        # No need for "Bitte zuerst Teams erstellen" if "Kein Team" is a valid primary state.
        # The admin workflow is to archive, then create new.
        self.team_id.choices = team_choices

LEITFADEN_CHOICES = [('Ja', 'Ja'), ('Nein', 'Nein'), ('k.A.', 'k.A.')]
COACHING_SUBJECT_CHOICES = [
    ('', '--- Bitte wählen ---'), 
    ('Sales', 'Sales'), ('Qualität', 'Qualität'), ('Allgemein', 'Allgemein') 
]

class CoachingForm(FlaskForm):
    team_member_id = SelectField(
        'Teammitglied (muss einem Team zugewiesen sein)', 
        coerce=int,
        validators=[DataRequired("Teammitglied ist erforderlich.")]
    )
    coaching_style = SelectField('Coaching Stil', choices=[('Side-by-Side', 'Side-by-Side'), ('TCAP', 'TCAP')], validators=[DataRequired("Coaching-Stil ist erforderlich.")])
    tcap_id = StringField('T-CAP ID (falls TCAP gewählt)', validators=[Optional(), Length(max=50)])
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
    coach_notes = TextAreaField('Notizen des Coaches', validators=[Optional(), Length(max=2000)])
    submit = SubmitField('Coaching speichern')

    def __init__(self, current_user_role=None, current_user_team_id=None, *args, **kwargs):
        super(CoachingForm, self).__init__(*args, **kwargs)
        generated_choices_final = [] # Use a different name to avoid conflict
        
        # Query for members who ARE currently assigned to a team (team_id IS NOT NULL)
        member_query = TeamMember.query.filter(TeamMember.team_id.isnot(None))

        if current_user_role == ROLE_TEAMLEITER and current_user_team_id:
            # Team leader can only coach members currently in their team
            team_members = member_query.filter_by(team_id=current_user_team_id).order_by(TeamMember.name).all()
            for m in team_members:
                generated_choices_final.append((m.id, m.name))
        elif current_user_role in [ROLE_ADMIN, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_PROJEKTLEITER, ROLE_ABTEILUNGSLEITER]:
            # These roles can coach any member currently assigned to any team
            # Use .join(Team) to ensure member.current_team is efficiently loaded for team name
            members_with_teams = member_query.join(TeamMember.current_team).order_by(Team.name, TeamMember.name).all()
            
            current_optgroup_label = None
            optgroup_members = []
            for m in members_with_teams:
                if m.current_team: # Should always be true due to filter and join
                    team_name_for_optgroup = m.current_team.name
                    if current_optgroup_label != team_name_for_optgroup:
                        if optgroup_members: # Add previous optgroup
                            generated_choices_final.append((current_optgroup_label, optgroup_members))
                        current_optgroup_label = team_name_for_optgroup
                        optgroup_members = []
                    optgroup_members.append((m.id, m.name))
            if optgroup_members: # Add the last optgroup
                generated_choices_final.append((current_optgroup_label, optgroup_members))
        
        if not generated_choices_final:
            self.team_member_id.choices = [("", "Keine Teammitglieder einem Team zugewiesen")]
        else:
            # Add a placeholder; optgroups are handled by WTForms if choices is a list of (group_label, options_list)
            # For flat list (TeamLeader), it's just a list of (value, label)
            self.team_member_id.choices = [("", "--- Bitte wählen ---")] + generated_choices_final

    def validate_team_member_id(self, field): # Custom validator
        if field.data and field.data != "": # If a value is selected (and not the placeholder)
            try:
                member_id_int = int(field.data) # coerce=int should handle this, but double check
                member = TeamMember.query.get(member_id_int)
                if not member:
                    raise ValidationError('Ausgewähltes Teammitglied nicht gefunden.')
                if member.team_id is None: # Check if member is assigned to a team
                    raise ValidationError('Mitglied ist keinem Team zugewiesen. Coaching nicht möglich.')
            except ValueError:
                raise ValidationError('Ungültige Teammitglied-ID.') # Should not happen with coerce=int

class ProjectLeaderNoteForm(FlaskForm):
    notes = TextAreaField('PL/QM Notiz', 
                          validators=[DataRequired("Die Notiz darf nicht leer sein."), 
                                      Length(max=2000)])
