from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import User, Team, TeamMember
from app.forms import RegistrationForm, TeamForm, TeamMemberForm
from app.utils import role_required, ROLE_ADMIN

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
    # Dynamisch Teams für das SelectField laden
    form.team_id.choices = [(0, 'Kein Team')] + [(t.id, t.name) for t in Team.query.order_by(Team.name).all()]

    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data, role=form.role.data)
        user.set_password(form.password.data)
        if form.role.data == 'Teamleiter' and form.team_id.data != 0:
            user.team_id = form.team_id.data # Direktes Team für den Leiter speichern
        db.session.add(user)
        db.session.commit()
        flash('Benutzer erfolgreich erstellt!', 'success')
        return redirect(url_for('admin.panel'))
    return render_template('admin/create_user.html', title='Benutzer erstellen', form=form)

@bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = RegistrationForm(obj=user) # Vorhandene Daten laden
    # Dynamisch Teams für das SelectField laden
    form.team_id.choices = [(0, 'Kein Team')] + [(t.id, t.name) for t in Team.query.order_by(Team.name).all()]
    
    # Passwortfelder sind optional beim Editieren
    form.password.validators = []
    form.password2.validators = []


    if form.validate_on_submit():
        user.username = form.username.data
        user.email = form.email.data
        user.role = form.role.data
        if form.role.data == 'Teamleiter' and form.team_id.data != 0:
            user.team_id = form.team_id.data
        else:
            user.team_id = None # Wichtig, falls Rolle kein TL mehr ist oder kein Team gewählt

        if form.password.data: # Nur wenn ein neues Passwort eingegeben wurde
            user.set_password(form.password.data)
        
        db.session.commit()
        flash('Benutzer erfolgreich aktualisiert!', 'success')
        return redirect(url_for('admin.panel'))
    elif request.method == 'GET': # Vorbelegen der Formulardaten
        form.username.data = user.username
        form.email.data = user.email
        form.role.data = user.role
        form.team_id.data = user.team_id if user.team_id else 0
    return render_template('admin/edit_user.html', title='Benutzer bearbeiten', form=form, user=user)


@bp.route('/users/delete/<int:user_id>', methods=['POST']) # Nur POST, um versehentliches Löschen per GET zu verhindern
@login_required
@role_required(ROLE_ADMIN)
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.username == 'admin' or user.id == current_user.id: # Admin oder sich selbst nicht löschen
        flash('Dieser Benutzer kann nicht gelöscht werden.', 'danger')
        return redirect(url_for('admin.panel'))
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
        if form.team_leader_id.data and form.team_leader_id.data != 0 :
            leader = User.query.get(form.team_leader_id.data)
            if leader and leader.role == 'Teamleiter':
                team.team_leader_id = leader.id
                leader.team_id = team.id # Auch beim User das Team setzen
            else:
                flash('Ausgewählter Benutzer ist kein Teamleiter oder existiert nicht.', 'warning')
        db.session.add(team)
        db.session.commit()
        flash('Team erfolgreich erstellt!', 'success')
        return redirect(url_for('admin.panel'))
    return render_template('admin/create_team.html', title='Team erstellen', form=form)

@bp.route('/teams/edit/<int:team_id>', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def edit_team(team_id):
    team = Team.query.get_or_404(team_id)
    form = TeamForm(obj=team)
    
    if form.validate_on_submit():
        team.name = form.name.data
        
        old_leader_id = team.team_leader_id
        new_leader_id = form.team_leader_id.data if form.team_leader_id.data != 0 else None

        # Alten Leader entkoppeln, falls er existiert und geändert wurde
        if old_leader_id and old_leader_id != new_leader_id:
            old_leader = User.query.get(old_leader_id)
            if old_leader:
                old_leader.team_id = None # Teamzuweisung entfernen

        team.team_leader_id = new_leader_id
        
        # Neuen Leader koppeln
        if new_leader_id:
            new_leader = User.query.get(new_leader_id)
            if new_leader and new_leader.role == 'Teamleiter':
                new_leader.team_id = team.id
            else:
                flash('Neuer ausgewählter Benutzer ist kein Teamleiter oder existiert nicht. Teamleiter nicht geändert.', 'warning')
                team.team_leader_id = old_leader_id # Zurücksetzen auf alten Wert, falls neuer ungültig

        db.session.commit()
        flash('Team erfolgreich aktualisiert!', 'success')
        return redirect(url_for('admin.panel'))
    elif request.method == 'GET':
        form.name.data = team.name
        form.team_leader_id.data = team.team_leader_id if team.team_leader_id else 0

    return render_template('admin/edit_team.html', title='Team bearbeiten', form=form, team=team)


@bp.route('/teams/delete/<int:team_id>', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def delete_team(team_id):
    team = Team.query.get_or_404(team_id)
    # Prüfen, ob Teammitglieder oder Coachings mit dem Team verbunden sind, bevor gelöscht wird
    if team.members.count() > 0:
        flash('Team kann nicht gelöscht werden, da ihm noch Mitglieder zugeordnet sind.', 'danger')
        return redirect(url_for('admin.panel'))
    # Coachings sind an Mitglieder gebunden, nicht direkt an Teams, also ist obiger Check ausreichend.
    # Ggf. Teamleiter entkoppeln
    if team.team_leader:
        team.team_leader.team_id = None
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
    if not form.team_id.choices or (len(form.team_id.choices) == 1 and form.team_id.choices[0][0] == 0) :
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
    form = TeamMemberForm(obj=member)

    if form.validate_on_submit():
        member.name = form.name.data
        member.team_id = form.team_id.data
        db.session.commit()
        flash('Teammitglied erfolgreich aktualisiert!', 'success')
        return redirect(url_for('admin.panel'))
    elif request.method == 'GET':
        form.name.data = member.name
        form.team_id.data = member.team_id
    return render_template('admin/edit_team_member.html', title='Teammitglied bearbeiten', form=form, member=member)


@bp.route('/teammembers/delete/<int:member_id>', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def delete_team_member(member_id):
    member = TeamMember.query.get_or_404(member_id)
    # Prüfen, ob Coachings mit dem Mitglied verbunden sind
    if member.coachings_received.count() > 0:
        flash('Teammitglied kann nicht gelöscht werden, da bereits Coachings für dieses Mitglied existieren.', 'danger')
        return redirect(url_for('admin.panel'))
    db.session.delete(member)
    db.session.commit()
    flash('Teammitglied gelöscht.', 'success')
    return redirect(url_for('admin.panel'))