# app/admin.py
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import User, Team, TeamMember # Stelle sicher, dass alle Modelle importiert sind
from app.forms import RegistrationForm, TeamForm, TeamMemberForm
from app.utils import role_required, ROLE_ADMIN, ROLE_TEAMLEITER # Importiere ROLE_TEAMLEITER

bp = Blueprint('admin', __name__)

@bp.route('/')
@login_required
@role_required(ROLE_ADMIN)
def panel():
    users = User.query.order_by(User.username).all()
    teams = Team.query.order_by(Team.name).all()
    team_members = TeamMember.query.order_by(TeamMember.name).all()
    return render_template('admin/admin_panel.html', title='Admin Panel',
                           users=users, teams=teams, team_members=team_members)

# --- User Management ---
@bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def create_user():
    form = RegistrationForm() 
    # Der __init__ der RegistrationForm sollte original_username und original_email als None übergeben bekommen,
    # oder wir müssen die Form-Initialisierung anpassen, um diese optional zu machen.
    # Für create_user ist es einfacher, wenn die Validatoren nicht auf original_... angewiesen sind.
    # Die aktuelle RegistrationForm __init__ nimmt keine original_... Parameter.
    
    # Dynamisch Teams für das SelectField laden
    active_teams = Team.query.order_by(Team.name).all()
    form.team_id.choices = [(t.id, t.name) for t in active_teams]
    form.team_id.choices.insert(0, (0, 'Kein Team'))
    if not active_teams and len(form.team_id.choices) == 1:
        form.team_id.choices = [(0, 'Zuerst Teams erstellen')]


    if form.validate_on_submit():
        print("DEBUG: create_user - Formular validiert.") # DEBUG
        try:
            user = User(
                username=form.username.data, 
                email=form.email.data if form.email.data else None, 
                role=form.role.data
            )
            user.set_password(form.password.data)
            
            db.session.add(user) # <--- DIES HAT GEFEHLT! USER MUSS ZUR SESSION HINZUGEFÜGT WERDEN
            print(f"DEBUG: User-Objekt vor erstem Commit (create): {user.__dict__}") # DEBUG
            db.session.commit() # Ersten Commit, damit der User eine ID bekommt
            print(f"DEBUG: User-Objekt nach erstem Commit (create), ID: {user.id}") # DEBUG

            # Teamleiter-Zuweisungslogik NACHDEM der User eine ID hat
            if user.role == ROLE_TEAMLEITER and form.team_id.data and int(form.team_id.data) != 0:
                team_to_assign = Team.query.get(int(form.team_id.data))
                if team_to_assign:
                    # Alten Teamleiter vom Team entbinden, falls vorhanden
                    if team_to_assign.team_leader_id and team_to_assign.team_leader_id != user.id:
                        old_leader = User.query.get(team_to_assign.team_leader_id)
                        if old_leader:
                            old_leader.team_id_if_leader = None
                            print(f"DEBUG: Alter Teamleiter {old_leader.username} von Team {team_to_assign.name} entbunden.")
                    
                    user.team_id_if_leader = team_to_assign.id
                    team_to_assign.team_leader_id = user.id # Team dem neuen Leiter zuweisen
                    db.session.commit() # Commit für User- und Team-Update
                    print(f"DEBUG: User {user.username} als TL für Team {team_to_assign.name} gesetzt. User.team_id_if_leader={user.team_id_if_leader}, Team.team_leader_id={team_to_assign.team_leader_id}")
            
            flash('Benutzer erfolgreich erstellt!', 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback()
            print(f"FEHLER beim Erstellen des Benutzers: {str(e)}") # DEBUG
            import traceback
            traceback.print_exc() # Gibt den vollen Traceback aus
            flash(f'Fehler beim Erstellen des Benutzers: {str(e)}', 'danger')
    elif request.method == 'POST': # Wenn Validierung fehlschlägt
        print("DEBUG: create_user - Formular-Validierung fehlgeschlagen.") # DEBUG
        for field, errors in form.errors.items():
            for error in errors:
                print(f"DEBUG: Fehler im Feld '{field}': {error}") # DEBUG
                flash(f"Fehler im Feld '{field}': {error}", 'danger')


    return render_template('admin/create_user.html', title='Benutzer erstellen', form=form)

@bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def edit_user(user_id):
    user_to_edit = User.query.get_or_404(user_id)
    # Übergebe original_username an das Formular, damit validate_username korrekt funktioniert
    form = RegistrationForm(obj=user_to_edit, original_username=user_to_edit.username) 
    
    # Passwortfelder sind optional beim Editieren - Validatoren entfernen, wenn keine neuen Daten da sind
    if not form.password.data:
        form.password.validators = []
    if not form.password2.data:
        form.password2.validators = []
    
    # Dynamisch Teams für das SelectField laden
    active_teams = Team.query.order_by(Team.name).all()
    form.team_id.choices = [(t.id, t.name) for t in active_teams]
    form.team_id.choices.insert(0, (0, 'Kein Team'))
    if not active_teams and len(form.team_id.choices) == 1: # Fallback
        form.team_id.choices = [(0, 'Zuerst Teams erstellen')]


    if form.validate_on_submit():
        print(f"DEBUG: edit_user - Formular validiert für User {user_to_edit.username}.") # DEBUG
        try:
            original_team_id_if_leader = user_to_edit.team_id_if_leader
            original_role = user_to_edit.role

            user_to_edit.username = form.username.data
            user_to_edit.email = form.email.data if form.email.data else None
            user_to_edit.role = form.role.data
            
            new_team_id_from_form = int(form.team_id.data) if form.team_id.data else 0

            if user_to_edit.role == ROLE_TEAMLEITER and new_team_id_from_form != 0:
                user_to_edit.team_id_if_leader = new_team_id_from_form
            else: # Kein Teamleiter oder "Kein Team" ausgewählt
                user_to_edit.team_id_if_leader = None
            
            if form.password.data:
                user_to_edit.set_password(form.password.data)
            
            print(f"DEBUG: User-Objekt vor Commit (edit): {user_to_edit.__dict__}") # DEBUG
            db.session.commit()
            print(f"DEBUG: User-Objekt nach Commit (edit), ID: {user_to_edit.id}") # DEBUG

            # Logik zur Aktualisierung der Team.team_leader_id Beziehung
            # Fall 1: User ist jetzt Teamleiter und hat ein Team zugewiesen
            if user_to_edit.role == ROLE_TEAMLEITER and user_to_edit.team_id_if_leader:
                assigned_team = Team.query.get(user_to_edit.team_id_if_leader)
                if assigned_team:
                    if assigned_team.team_leader_id != user_to_edit.id: # Wenn das Team einen anderen Leiter hatte oder keinen
                        if assigned_team.team_leader_id: # Wenn es einen alten Leiter gab
                            old_leader = User.query.get(assigned_team.team_leader_id)
                            if old_leader: old_leader.team_id_if_leader = None # Alten Leiter vom Team lösen
                        assigned_team.team_leader_id = user_to_edit.id
                        print(f"DEBUG: Team {assigned_team.name} TL auf {user_to_edit.username} gesetzt.")
                        db.session.commit()

            # Fall 2: User war Teamleiter, ist es aber nicht mehr, ODER war TL und hat jetzt kein Team mehr
            elif (original_role == ROLE_TEAMLEITER and user_to_edit.role != ROLE_TEAMLEITER and original_team_id_if_leader) or \
                 (original_role == ROLE_TEAMLEITER and user_to_edit.role == ROLE_TEAMLEITER and not user_to_edit.team_id_if_leader and original_team_id_if_leader):
                old_team = Team.query.get(original_team_id_if_leader)
                if old_team and old_team.team_leader_id == user_to_edit.id:
                    old_team.team_leader_id = None
                    print(f"DEBUG: User {user_to_edit.username} als TL von Team {old_team.name} entfernt.")
                    db.session.commit()
            
            # Fall 3: User ist Teamleiter und wurde von einem anderen Team zu diesem Team gewechselt
            if original_role == ROLE_TEAMLEITER and original_team_id_if_leader and \
               user_to_edit.role == ROLE_TEAMLEITER and user_to_edit.team_id_if_leader and \
               original_team_id_if_leader != user_to_edit.team_id_if_leader:
                old_team = Team.query.get(original_team_id_if_leader)
                if old_team and old_team.team_leader_id == user_to_edit.id: # Sicherstellen, dass er wirklich der Leiter war
                    old_team.team_leader_id = None # Vom alten Team entfernen
                    print(f"DEBUG: User {user_to_edit.username} als TL von altem Team {old_team.name} entfernt (Teamwechsel).")
                    db.session.commit()


            flash('Benutzer erfolgreich aktualisiert!', 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback()
            print(f"FEHLER beim Aktualisieren des Benutzers: {str(e)}") # DEBUG
            import traceback
            traceback.print_exc()
            flash(f'Fehler beim Aktualisieren des Benutzers: {str(e)}', 'danger')
    elif request.method == 'GET':
        form.username.data = user_to_edit.username
        form.email.data = user_to_edit.email
        form.role.data = user_to_edit.role
        form.team_id.data = user_to_edit.team_id_if_leader if user_to_edit.team_id_if_leader else 0
    
    return render_template('admin/edit_user.html', title='Benutzer bearbeiten', form=form, user=user_to_edit)


@bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.username == 'admin' or user.id == current_user.id:
        flash('Dieser Benutzer kann nicht gelöscht werden.', 'danger')
        return redirect(url_for('admin.panel'))
    
    # Wenn der User Teamleiter ist, ihn vom Team entbinden
    if user.role == ROLE_TEAMLEITER and user.team_id_if_leader:
        team_led = Team.query.get(user.team_id_if_leader)
        if team_led and team_led.team_leader_id == user.id:
            team_led.team_leader_id = None
            # user.team_id_if_leader wird durch das Löschen des Users irrelevant

    # Coachings, die dieser User als Coach durchgeführt hat, anonymisieren oder löschen?
    # Hier: wir löschen den User, DB-Constraints (ON DELETE) sollten greifen oder Fehler werfen.
    # Besser wäre es, Coachings zu anonymisieren (coach_id auf NULL setzen, falls erlaubt)
    # oder das Löschen zu verhindern, wenn noch Coachings existieren.
    # Für jetzt: DB-Constraints regeln lassen.
    # Coaching.query.filter_by(coach_id=user_id).update({'coach_id': None}) # Beispiel für Anonymisierung

    db.session.delete(user)
    db.session.commit()
    flash('Benutzer gelöscht.', 'success')
    return redirect(url_for('admin.panel'))

# --- Team Management ---
@bp.route('/teams/create', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def create_team():
    form = TeamForm()
    if form.validate_on_submit():
        team = Team(name=form.name.data)
        db.session.add(team)
        db.session.commit() # Commit, damit Team eine ID hat

        if form.team_leader_id.data and int(form.team_leader_id.data) != 0 :
            leader = User.query.get(int(form.team_leader_id.data))
            if leader and leader.role == ROLE_TEAMLEITER:
                # Alten Teamleiter vom bisherigen Team entbinden, falls er eines hatte
                if leader.team_id_if_leader:
                    old_team_of_leader = Team.query.get(leader.team_id_if_leader)
                    if old_team_of_leader:
                        old_team_of_leader.team_leader_id = None
                
                team.team_leader_id = leader.id
                leader.team_id_if_leader = team.id 
                db.session.commit() # Commit für die Zuweisungen
                print(f"DEBUG: Team {team.name} erstellt und TL {leader.username} zugewiesen.")
            else:
                flash('Ausgewählter Benutzer ist kein Teamleiter oder existiert nicht. Team ohne Leiter erstellt.', 'warning')
        else:
             print(f"DEBUG: Team {team.name} ohne Teamleiter erstellt.")
        
        flash('Team erfolgreich erstellt!', 'success')
        return redirect(url_for('admin.panel'))
    return render_template('admin/create_team.html', title='Team erstellen', form=form)

@bp.route('/teams/edit/<int:team_id>', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def edit_team(team_id_param): # Umbenannt, um Kollision mit team_id Variable zu vermeiden
    team_to_edit = Team.query.get_or_404(team_id_param)
    form = TeamForm(obj=team_to_edit)
    
    if form.validate_on_submit():
        team_to_edit.name = form.name.data
        
        new_leader_id = int(form.team_leader_id.data) if form.team_leader_id.data else 0
        old_leader_id = team_to_edit.team_leader_id

        # Wenn der Teamleiter geändert wird
        if new_leader_id != old_leader_id:
            # Alten Teamleiter vom aktuellen Team entbinden
            if old_leader_id:
                old_leader = User.query.get(old_leader_id)
                if old_leader:
                    old_leader.team_id_if_leader = None 
            
            # Neuen Teamleiter zuweisen (falls einer ausgewählt wurde)
            if new_leader_id != 0:
                new_leader = User.query.get(new_leader_id)
                if new_leader and new_leader.role == ROLE_TEAMLEITER:
                    # Neuen Teamleiter von seinem eventuell alten Team entbinden
                    if new_leader.team_id_if_leader and new_leader.team_id_if_leader != team_to_edit.id:
                        previous_team_of_new_leader = Team.query.get(new_leader.team_id_if_leader)
                        if previous_team_of_new_leader:
                            previous_team_of_new_leader.team_leader_id = None
                    
                    team_to_edit.team_leader_id = new_leader.id
                    new_leader.team_id_if_leader = team_to_edit.id
                else:
                    flash('Neuer ausgewählter Benutzer ist kein Teamleiter oder existiert nicht. Teamleiter nicht geändert.', 'warning')
                    team_to_edit.team_leader_id = old_leader_id # Zurücksetzen, falls neuer ungültig
            else: # Kein Teamleiter ausgewählt
                team_to_edit.team_leader_id = None
        
        db.session.commit()
        flash('Team erfolgreich aktualisiert!', 'success')
        return redirect(url_for('admin.panel'))
    elif request.method == 'GET':
        form.name.data = team_to_edit.name
        form.team_leader_id.data = team_to_edit.team_leader_id if team_to_edit.team_leader_id else 0

    return render_template('admin/edit_team.html', title='Team bearbeiten', form=form, team=team_to_edit)

# ... (Rest der Datei: delete_team, TeamMember Management bleiben erstmal so, 
#      aber beachte, dass dort auch user.team_id zu user.team_id_if_leader werden muss, 
#      wenn du auf das Team zugreifst, das ein User leitet) ...

@bp.route('/teams/delete/<int:team_id>', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def delete_team(team_id):
    team = Team.query.get_or_404(team_id)
    if team.members.count() > 0:
        flash('Team kann nicht gelöscht werden, da ihm noch Mitglieder zugeordnet sind.', 'danger')
        return redirect(url_for('admin.panel'))
    
    if team.team_leader: # Wenn das Team einen Leiter hat
        team.team_leader.team_id_if_leader = None # Entferne die Referenz vom User zum Team
        # team.team_leader_id wird durch das Löschen des Teams irrelevant

    db.session.delete(team)
    db.session.commit()
    flash('Team gelöscht.', 'success')
    return redirect(url_for('admin.panel'))

# --- Team Member Management ---
@bp.route('/teammembers/create', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def create_team_member():
    form = TeamMemberForm()
    if not form.team_id.choices or \
       (len(form.team_id.choices) == 1 and form.team_id.choices[0][0] == 0 and form.team_id.choices[0][1] != "Bitte zuerst Teams erstellen"):
        # Diese Bedingung ist etwas komplex, um sicherzustellen, dass nicht nur die "Kein Team"-Option da ist.
        # Einfacher: Prüfen, ob echte Teams in den Choices sind.
        if not any(choice[0] != 0 for choice in form.team_id.choices):
             flash("Bitte erstellen Sie zuerst mindestens ein Team.", "warning")
             return redirect(url_for('admin.panel'))


    if form.validate_on_submit():
        member = TeamMember(name=form.name.data, team_id=form.team_id.data)
        db.session.add(member)
        db.session.commit()
        flash('Teammitglied erfolgreich erstellt!', 'success')
        return redirect(url_for('admin.panel'))
    return render_template('admin/create_team_member.html', title='Teammitglied erstellen', form=form)


@bp.route('/teammembers/edit/<int:member_id>', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def edit_team_member(member_id):
    member = TeamMember.query.get_or_404(member_id)
    form = TeamMemberForm(obj=member) # Hier werden die team_id choices im __init__ des Forms neu geladen

    if form.validate_on_submit():
        member.name = form.name.data
        member.team_id = form.team_id.data
        db.session.commit()
        flash('Teammitglied erfolgreich aktualisiert!', 'success')
        return redirect(url_for('admin.panel'))
    # Beim GET-Request werden die Daten bereits durch obj=member im Formular gesetzt.
    # Zusätzliches form.name.data = member.name ist nicht nötig, wenn obj verwendet wird.
    # Die choices für team_id werden im __init__ der Form geladen.
    # Wir müssen aber sicherstellen, dass der aktuelle Wert des Members im Formular ausgewählt ist.
    elif request.method == 'GET':
        form.team_id.data = member.team_id # Stellt sicher, dass das richtige Team vorausgewählt ist

    return render_template('admin/edit_team_member.html', title='Teammitglied bearbeiten', form=form, member=member)


@bp.route('/teammembers/delete/<int:member_id>', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def delete_team_member(member_id):
    member = TeamMember.query.get_or_404(member_id)
    if member.coachings_received.count() > 0:
        flash('Teammitglied kann nicht gelöscht werden, da bereits Coachings für dieses Mitglied existieren.', 'danger')
        return redirect(url_for('admin.panel'))
    db.session.delete(member)
    db.session.commit()
    flash('Teammitglied gelöscht.', 'success')
    return redirect(url_for('admin.panel'))