# app/admin.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from sqlalchemy import desc, or_
from app import db
from app.models import User, Team, TeamMember, Coaching # Ensure Coaching is imported
from app.forms import RegistrationForm, TeamForm, TeamMemberForm, CoachingForm # Import CoachingForm

# <<< GEÄNDERT >>> Importiere die neue Hilfsfunktion und die Konstante
from app.utils import role_required, ROLE_ADMIN, ROLE_TEAMLEITER, get_or_create_archiv_team, ARCHIV_TEAM_NAME

# Import helpers from main_routes (ensure main_routes.py has these accessible or define them here)
from app.main_routes import calculate_date_range, get_month_name_german
from datetime import datetime, timezone # For month_options generation

bp = Blueprint('admin', __name__)

@bp.route('/')
@login_required
@role_required(ROLE_ADMIN)
def panel():
    # <<< GEÄNDERT >>> Schließe das ARCHIV-Team von der Hauptliste aus
    users = User.query.order_by(User.username).all()
    teams = Team.query.filter(Team.name != ARCHIV_TEAM_NAME).order_by(Team.name).all()
    team_members = TeamMember.query.order_by(TeamMember.name).all()
    
    # Finde archivierte Mitglieder separat, um sie optional anzuzeigen
    archiv_team = Team.query.filter_by(name=ARCHIV_TEAM_NAME).first()
    archived_members = archiv_team.members.all() if archiv_team else []

    return render_template('admin/admin_panel.html', title='Admin Panel',
                           users=users, teams=teams, team_members=team_members, 
                           archived_members=archived_members, # <<< NEU >>>
                           config=current_app.config)

# --- User Management ---
@bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def create_user():
    form = RegistrationForm()
    # <<< GEÄNDERT >>> Schließe das ARCHIV-Team aus der Auswahl aus
    active_teams = Team.query.filter(Team.name != ARCHIV_TEAM_NAME).order_by(Team.name).all()
    form.team_id.choices = [(t.id, t.name) for t in active_teams]
    form.team_id.choices.insert(0, (0, 'Kein Team'))
    if not active_teams and len(form.team_id.choices) == 1:
        form.team_id.choices = [(0, 'Zuerst Teams erstellen')]

    if form.validate_on_submit():
        try:
            user = User(
                username=form.username.data,
                email=form.email.data if form.email.data else None,
                role=form.role.data
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()

            if user.role == ROLE_TEAMLEITER and form.team_id.data and int(form.team_id.data) != 0:
                team_to_assign = Team.query.get(int(form.team_id.data))
                if team_to_assign:
                    if team_to_assign.team_leader_id and team_to_assign.team_leader_id != user.id:
                        old_leader = User.query.get(team_to_assign.team_leader_id)
                        if old_leader:
                            old_leader.team_id_if_leader = None
                    user.team_id_if_leader = team_to_assign.id
                    team_to_assign.team_leader_id = user.id
                    db.session.commit()
            flash('Benutzer erfolgreich erstellt!', 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"FEHLER beim Erstellen des Benutzers: {str(e)}")
            import traceback
            traceback.print_exc()
            flash(f'Fehler beim Erstellen des Benutzers: {str(e)}', 'danger')
    elif request.method == 'POST':
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Fehler im Feld '{form[field].label.text if hasattr(form[field], 'label') else field}': {error}", 'danger')
    return render_template('admin/create_user.html', title='Benutzer erstellen', form=form, config=current_app.config)

@bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def edit_user(user_id):
    user_to_edit = User.query.get_or_404(user_id)
    form = RegistrationForm(obj=user_to_edit, original_username=user_to_edit.username)

    if not form.password.data:
        form.password.validators = []
        form.password2.validators = []
    elif not form.password2.data and form.password.data:
         pass

    # <<< GEÄNDERT >>> Schließe das ARCHIV-Team aus der Auswahl aus
    active_teams = Team.query.filter(Team.name != ARCHIV_TEAM_NAME).order_by(Team.name).all()
    form.team_id.choices = [(t.id, t.name) for t in active_teams]
    form.team_id.choices.insert(0, (0, 'Kein Team'))
    if not active_teams and len(form.team_id.choices) == 1:
        form.team_id.choices = [(0, 'Zuerst Teams erstellen')]

    if form.validate_on_submit():
        try:
            original_team_id_if_leader = user_to_edit.team_id_if_leader
            original_role = user_to_edit.role
            user_to_edit.username = form.username.data
            user_to_edit.email = form.email.data if form.email.data else None
            user_to_edit.role = form.role.data
            new_team_id_from_form = int(form.team_id.data) if form.team_id.data and str(form.team_id.data).isdigit() else 0

            if user_to_edit.role == ROLE_TEAMLEITER and new_team_id_from_form != 0:
                user_to_edit.team_id_if_leader = new_team_id_from_form
            else:
                user_to_edit.team_id_if_leader = None
            
            if form.password.data:
                user_to_edit.set_password(form.password.data)
            
            db.session.commit()

            if user_to_edit.role == ROLE_TEAMLEITER and user_to_edit.team_id_if_leader:
                assigned_team = Team.query.get(user_to_edit.team_id_if_leader)
                if assigned_team:
                    if assigned_team.team_leader_id != user_to_edit.id:
                        if assigned_team.team_leader_id:
                            old_leader_on_team = User.query.get(assigned_team.team_leader_id)
                            if old_leader_on_team: old_leader_on_team.team_id_if_leader = None
                        assigned_team.team_leader_id = user_to_edit.id
                        db.session.commit()
            
            if original_role == ROLE_TEAMLEITER and original_team_id_if_leader:
                if (user_to_edit.role != ROLE_TEAMLEITER) or \
                   (user_to_edit.role == ROLE_TEAMLEITER and user_to_edit.team_id_if_leader != original_team_id_if_leader):
                    old_team_assignment = Team.query.get(original_team_id_if_leader)
                    if old_team_assignment and old_team_assignment.team_leader_id == user_to_edit.id:
                        old_team_assignment.team_leader_id = None
                        db.session.commit()
            
            flash('Benutzer erfolgreich aktualisiert!', 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"FEHLER beim Aktualisieren des Benutzers: {str(e)}")
            import traceback
            traceback.print_exc()
            flash(f'Fehler beim Aktualisieren des Benutzers: {str(e)}', 'danger')
    elif request.method == 'GET':
        form.username.data = user_to_edit.username
        form.email.data = user_to_edit.email
        form.role.data = user_to_edit.role
        form.team_id.data = user_to_edit.team_id_if_leader if user_to_edit.team_id_if_leader else 0
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Fehler im Feld '{form[field].label.text if hasattr(form[field], 'label') else field}': {error}", 'danger')
    
    return render_template('admin/edit_user.html', title='Benutzer bearbeiten', form=form, user=user_to_edit, config=current_app.config)

@bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.username == 'admin' or user.id == current_user.id:
        flash('Dieser Benutzer kann nicht gelöscht werden.', 'danger')
        return redirect(url_for('admin.panel'))
    
    try:
        if user.role == ROLE_TEAMLEITER and user.team_id_if_leader:
            team_led = Team.query.get(user.team_id_if_leader)
            if team_led and team_led.team_leader_id == user.id:
                team_led.team_leader_id = None
        
        Coaching.query.filter_by(coach_id=user_id).update({"coach_id": None})
        db.session.delete(user)
        db.session.commit()
        flash('Benutzer gelöscht.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Fehler beim Löschen von User ID {user_id}: {e}")
        flash(f'Fehler beim Löschen des Benutzers. Es könnten noch verbundene Daten existieren (z.B. Coachings). Details im Log.', 'danger')
    return redirect(url_for('admin.panel'))

# --- Team Management ---
@bp.route('/teams/create', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def create_team():
    form = TeamForm()
    if form.validate_on_submit():
        # <<< NEU >>> Verhindere die manuelle Erstellung eines Teams namens "ARCHIV"
        if form.name.data.strip().upper() == ARCHIV_TEAM_NAME:
            flash(f'Der Teamname "{ARCHIV_TEAM_NAME}" ist für das System reserviert.', 'danger')
            return render_template('admin/create_team.html', title='Team erstellen', form=form, config=current_app.config)
        try:
            team = Team(name=form.name.data)
            db.session.add(team)
            db.session.commit()
            if form.team_leader_id.data and int(form.team_leader_id.data) != 0 :
                leader = User.query.get(int(form.team_leader_id.data))
                if leader and leader.role == ROLE_TEAMLEITER:
                    if leader.team_id_if_leader:
                        old_team_of_leader = Team.query.get(leader.team_id_if_leader)
                        if old_team_of_leader:
                            old_team_of_leader.team_leader_id = None
                    team.team_leader_id = leader.id
                    leader.team_id_if_leader = team.id
                    db.session.commit()
                else:
                    flash('Ausgewählter Benutzer ist kein Teamleiter oder existiert nicht. Team ohne Leiter erstellt.', 'warning')
            
            flash('Team erfolgreich erstellt!', 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Fehler beim Erstellen des Teams: {e}")
            flash(f'Fehler beim Erstellen des Teams: {str(e)}', 'danger')
    return render_template('admin/create_team.html', title='Team erstellen', form=form, config=current_app.config)

@bp.route('/teams/edit/<int:team_id>', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def edit_team(team_id):
    team_to_edit = Team.query.get_or_404(team_id)
    form = TeamForm(obj=team_to_edit, original_name=team_to_edit.name)
    
    # <<< NEU >>> Verhindere das Umbenennen des ARCHIV-Teams
    if team_to_edit.name == ARCHIV_TEAM_NAME and request.method == 'GET':
        flash('Das ARCHIV-Team kann nicht bearbeitet werden.', 'info')
        # Deaktiviere Formularfelder für das Archiv-Team
        form.name.render_kw = {'readonly': True}
        form.team_leader_id.render_kw = {'disabled': True}

    if form.validate_on_submit():
        # <<< NEU >>> Zusätzliche Sicherheitsprüfung
        if team_to_edit.name == ARCHIV_TEAM_NAME:
            flash('Das ARCHIV-Team kann nicht geändert werden.', 'danger')
            return redirect(url_for('admin.edit_team', team_id=team_id))
            
        try:
            team_to_edit.name = form.name.data
            new_leader_id = int(form.team_leader_id.data) if form.team_leader_id.data and str(form.team_leader_id.data).isdigit() else 0
            old_leader_id = team_to_edit.team_leader_id

            if new_leader_id != old_leader_id:
                if old_leader_id:
                    old_leader = User.query.get(old_leader_id)
                    if old_leader: old_leader.team_id_if_leader = None
                
                if new_leader_id != 0:
                    new_leader = User.query.get(new_leader_id)
                    if new_leader and new_leader.role == ROLE_TEAMLEITER:
                        if new_leader.team_id_if_leader and new_leader.team_id_if_leader != team_to_edit.id:
                            previous_team_of_new_leader = Team.query.get(new_leader.team_id_if_leader)
                            if previous_team_of_new_leader: previous_team_of_new_leader.team_leader_id = None
                        team_to_edit.team_leader_id = new_leader.id
                        new_leader.team_id_if_leader = team_to_edit.id
                    else:
                        flash('Neuer ausgewählter Benutzer ist kein Teamleiter oder existiert nicht. Teamleiter nicht geändert.', 'warning')
                        team_to_edit.team_leader_id = old_leader_id
                else:
                    team_to_edit.team_leader_id = None
            
            db.session.commit()
            flash('Team erfolgreich aktualisiert!', 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Fehler beim Bearbeiten des Teams {team_id}: {e}")
            flash(f'Fehler beim Bearbeiten des Teams: {str(e)}', 'danger')

    elif request.method == 'GET':
        form.name.data = team_to_edit.name
        form.team_leader_id.data = team_to_edit.team_leader_id if team_to_edit.team_leader_id else 0
    
    return render_template('admin/edit_team.html', title='Team bearbeiten', form=form, team=team_to_edit, config=current_app.config)

@bp.route('/teams/delete/<int:team_id>', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def delete_team(team_id):
    team = Team.query.get_or_404(team_id)
    # <<< NEU >>> Verhindere das Löschen des ARCHIV-Teams
    if team.name == ARCHIV_TEAM_NAME:
        flash('Das ARCHIV-Team kann nicht gelöscht werden.', 'danger')
        return redirect(url_for('admin.panel'))
    if team.members.count() > 0:
        flash('Team kann nicht gelöscht werden, da ihm noch Mitglieder zugeordnet sind. Verschieben Sie die Mitglieder zuerst ins Archiv.', 'danger')
        return redirect(url_for('admin.panel'))
    
    try:
        if team.team_leader:
            team.team_leader.team_id_if_leader = None
        db.session.delete(team)
        db.session.commit()
        flash('Team gelöscht.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Fehler beim Löschen von Team ID {team_id}: {e}")
        flash('Fehler beim Löschen des Teams.', 'danger')
    return redirect(url_for('admin.panel'))

# --- Team Member Management ---
@bp.route('/teammembers/create', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def create_team_member():
    form = TeamMemberForm()
    # <<< GEÄNDERT >>> populate choices but exclude ARCHIV
    form.team_id.choices = [(t.id, t.name) for t in Team.query.filter(Team.name != ARCHIV_TEAM_NAME).order_by(Team.name).all()]
    if not form.team_id.choices:
        flash("Bitte erstellen Sie zuerst mindestens ein Team, bevor Sie Mitglieder hinzufügen.", "warning")
        return redirect(url_for('admin.create_team') if Team.query.count() <= 1 else url_for('admin.panel'))

    if form.validate_on_submit():
        try:
            member = TeamMember(name=form.name.data, team_id=form.team_id.data)
            db.session.add(member)
            db.session.commit()
            flash('Teammitglied erfolgreich erstellt!', 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Fehler beim Erstellen des Teammitglieds: {e}")
            flash(f'Fehler beim Erstellen des Teammitglieds: {str(e)}', 'danger')
    return render_template('admin/create_team_member.html', title='Teammitglied erstellen', form=form, config=current_app.config)

@bp.route('/teammembers/edit/<int:member_id>', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def edit_team_member(member_id):
    member = TeamMember.query.get_or_404(member_id)
    form = TeamMemberForm(obj=member)
    # <<< GEÄNDERT >>> populate choices but exclude ARCHIV
    form.team_id.choices = [(t.id, t.name) for t in Team.query.filter(Team.name != ARCHIV_TEAM_NAME).order_by(Team.name).all()]

    if form.validate_on_submit():
        try:
            member.name = form.name.data
            member.team_id = form.team_id.data
            db.session.commit()
            flash('Teammitglied erfolgreich aktualisiert!', 'success')
            # <<< GEÄNDERT >>> Redirect back to the team edit page for better workflow
            return redirect(url_for('admin.edit_team', team_id=member.team_id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Fehler beim Bearbeiten des Teammitglieds {member_id}: {e}")
            flash(f'Fehler beim Bearbeiten des Teammitglieds: {str(e)}', 'danger')
    elif request.method == 'GET':
        form.team_id.data = member.team_id

    return render_template('admin/edit_team_member.html', title='Teammitglied bearbeiten', form=form, member=member, config=current_app.config)

# <<< NEU >>> Route, um ein Mitglied ins ARCHIV zu verschieben
@bp.route('/teammembers/<int:member_id>/move-to-archiv', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def move_to_archiv(member_id):
    member_to_move = TeamMember.query.get_or_404(member_id)
    original_team_id = member_to_move.team_id
    original_team_name = member_to_move.team.name
    
    archiv_team = get_or_create_archiv_team()
    
    if member_to_move.team_id == archiv_team.id:
        flash(f'{member_to_move.name} ist bereits im Archiv.', 'info')
        return redirect(url_for('admin.panel'))

    try:
        member_to_move.team_id = archiv_team.id
        db.session.commit()
        flash(f'Mitglied "{member_to_move.name}" wurde von Team "{original_team_name}" ins ARCHIV verschoben.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Fehler beim Verschieben von Mitglied {member_id} ins Archiv: {e}")
        flash('Fehler beim Verschieben des Mitglieds ins Archiv.', 'danger')

    # Redirect back to the original team's edit page
    return redirect(url_for('admin.edit_team', team_id=original_team_id))


# <<< GEÄNDERT >>> Die alte delete_team_member Route wird durch das Archiv-System ersetzt.
# Wir kommentieren sie aus, anstatt sie zu löschen, falls die Logik später benötigt wird.
#
# @bp.route('/teammembers/delete/<int:member_id>', methods=['POST'])
# @login_required
# @role_required(ROLE_ADMIN)
# def delete_team_member(member_id):
#     member = TeamMember.query.get_or_404(member_id)
#     if member.coachings_received.count() > 0: # coachings_received is the backref from Coaching to TeamMember
#         flash('Teammitglied kann nicht gelöscht werden, da bereits Coachings für dieses Mitglied existieren. Verschieben Sie es stattdessen ins ARCHIV.', 'danger')
#         return redirect(url_for('admin.panel'))
#     try:
#         db.session.delete(member)
#         db.session.commit()
#         flash('Teammitglied gelöscht.', 'success')
#     except Exception as e:
#         db.session.rollback()
#         current_app.logger.error(f"Fehler beim Löschen von Teammitglied ID {member_id}: {e}")
#         flash('Fehler beim Löschen des Teammitglieds.', 'danger')
#     return redirect(url_for('admin.panel'))


# --- Coaching Management (Unverändert, aber hier zur Vollständigkeit) ---
@bp.route('/manage_coachings', methods=['GET', 'POST'])
@login_required
@role_required([ROLE_ADMIN])
def manage_coachings():
    # ... (Rest der Funktion bleibt unverändert)
    page = request.args.get('page', 1, type=int)
    period_filter_arg = request.args.get('period', 'all')
    team_filter_arg = request.args.get('team', 'all')
    team_member_filter_arg = request.args.get('teammember', 'all')
    coach_filter_arg = request.args.get('coach', 'all')
    search_term = request.args.get('search', default="", type=str).strip()

    coachings_query = Coaching.query \
        .join(TeamMember, Coaching.team_member_id == TeamMember.id) \
        .join(User, Coaching.coach_id == User.id, isouter=True) \
        .join(Team, TeamMember.team_id == Team.id)

    # <<< GEÄNDERT >>> Das ARCHIV-Team aus der Coaching-Verwaltung standardmäßig ausblenden
    if team_filter_arg == 'all':
         coachings_query = coachings_query.filter(Team.name != ARCHIV_TEAM_NAME)

    start_date, end_date = calculate_date_range(period_filter_arg)
    if start_date:
        coachings_query = coachings_query.filter(Coaching.coaching_date >= start_date)
    if end_date:
        coachings_query = coachings_query.filter(Coaching.coaching_date <= end_date)

    if team_filter_arg and team_filter_arg.isdigit():
        coachings_query = coachings_query.filter(TeamMember.team_id == int(team_filter_arg))
    if team_member_filter_arg and team_member_filter_arg.isdigit():
        coachings_query = coachings_query.filter(Coaching.team_member_id == int(team_member_filter_arg))
    if coach_filter_arg and coach_filter_arg.isdigit():
        coachings_query = coachings_query.filter(Coaching.coach_id == int(coach_filter_arg))
    
    if search_term:
        search_pattern = f"%{search_term}%"
        coachings_query = coachings_query.filter(
            or_(
                TeamMember.name.ilike(search_pattern),
                User.username.ilike(search_pattern),
                Team.name.ilike(search_pattern),
                Coaching.coaching_subject.ilike(search_pattern),
                Coaching.coaching_style.ilike(search_pattern),
                Coaching.tcap_id.ilike(search_pattern),
                Coaching.coach_notes.ilike(search_pattern),
                Coaching.project_leader_notes.ilike(search_pattern)
            )
        )
    
    if request.method == 'POST':
        if 'delete_selected' in request.form:
            coaching_ids_to_delete = request.form.getlist('coaching_ids')
            if coaching_ids_to_delete:
                try:
                    coaching_ids_to_delete_int = [int(id_str) for id_str in coaching_ids_to_delete]
                    deleted_count = Coaching.query.filter(Coaching.id.in_(coaching_ids_to_delete_int)).delete(synchronize_session='fetch')
                    db.session.commit()
                    flash(f'{deleted_count} Coaching(s) erfolgreich gelöscht.', 'success')
                except ValueError:
                    flash('Ungültige Coaching-IDs zum Löschen ausgewählt.', 'danger')
                except Exception as e:
                    db.session.rollback()
                    current_app.logger.error(f"Fehler beim Löschen von Coachings: {e}")
                    flash(f'Fehler beim Löschen der Coachings: {str(e)}', 'danger')
                return redirect(url_for('admin.manage_coachings', page=page, period=period_filter_arg, team=team_filter_arg,teammember=team_member_filter_arg,coach=coach_filter_arg,search=search_term))
            else:
                flash('Keine Coachings zum Löschen ausgewählt.', 'info')

    coachings_paginated = coachings_query.order_by(desc(Coaching.coaching_date))\
        .paginate(page=page, per_page=15, error_out=False)

    all_teams = Team.query.order_by(Team.name).all() # Hier alle anzeigen, inkl. ARCHIV für Filterung
    all_team_members = TeamMember.query.order_by(TeamMember.name).all()
    all_coaches = User.query.filter(User.coachings_done.any()).distinct().order_by(User.username).all()

    now_dt = datetime.now(timezone.utc)
    current_year_val = now_dt.year
    previous_year_val = current_year_val - 1
    month_options_for_filter = []
    for m_num in range(12, 0, -1):
        month_options_for_filter.append({'value': f"{previous_year_val}-{m_num:02d}", 'text': f"{get_month_name_german(m_num)} {previous_year_val}"})
    for m_num in range(now_dt.month, 0, -1): 
        month_options_for_filter.append({'value': f"{current_year_val}-{m_num:02d}", 'text': f"{get_month_name_german(m_num)} {current_year_val}"})


    return render_template('admin/manage_coachings.html', 
                           title='Coachings Verwalten',
                           coachings_paginated=coachings_paginated,
                           all_teams=all_teams,
                           all_team_members=all_team_members,
                           all_coaches=all_coaches,
                           month_options=month_options_for_filter,
                           current_period_filter=period_filter_arg,
                           current_team_id_filter=team_filter_arg,
                           current_teammember_id_filter=team_member_filter_arg,
                           current_coach_id_filter=coach_filter_arg,
                           current_search_term=search_term,
                           config=current_app.config,
                           ARCHIV_TEAM_NAME=ARCHIV_TEAM_NAME) # <<< NEU >>> an Template übergeben

# ... (Rest der Datei bleibt gleich) ...
@bp.route('/coaching/<int:coaching_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required([ROLE_ADMIN])
def edit_coaching_entry(coaching_id):
    coaching_to_edit = Coaching.query.get_or_404(coaching_id)
    form = CoachingForm(obj=coaching_to_edit, current_user_role=ROLE_ADMIN, current_user_team_id=None)

    if form.validate_on_submit():
        try:
            form.populate_obj(coaching_to_edit)
            db.session.commit()
            flash(f'Coaching ID {coaching_id} erfolgreich aktualisiert!', 'success')
            return redirect(url_for('admin.manage_coachings'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating coaching ID {coaching_id}: {e}")
            flash(f'Fehler beim Aktualisieren von Coaching ID {coaching_id}.', 'danger')
    elif request.method == 'GET':
        pass

    if request.method == 'GET' or not form.validate_on_submit():
        generated_choices = []
        all_teams = Team.query.order_by(Team.name).all() # Alle Teams inkl. Archiv, damit alte Einträge bearbeitbar bleiben
        for team_obj_form in all_teams:
            members = TeamMember.query.filter_by(team_id=team_obj_form.id).order_by(TeamMember.name).all()
            for m in members:
                generated_choices.append((m.id, f"{m.name} ({team_obj_form.name})"))
        
        if not generated_choices:
            form.team_member_id.choices = []
        else:
            form.team_member_id.choices = generated_choices
        
        form.team_member_id.data = coaching_to_edit.team_member_id

    tcap_js_for_edit = """ ... """ # (unverändert)
    return render_template('main/add_coaching.html', 
                            title=f'Coaching ID {coaching_id} bearbeiten', 
                            form=form, 
                            is_edit_mode=True,
                            coaching=coaching_to_edit,
                            tcap_js=tcap_js_for_edit,
                            config=current_app.config)

@bp.route('/coaching/<int:coaching_id>/delete', methods=['POST'])
@login_required
@role_required([ROLE_ADMIN])
def delete_coaching_entry(coaching_id):
    coaching = Coaching.query.get_or_404(coaching_id)
    try:
        db.session.delete(coaching)
        db.session.commit()
        flash(f'Coaching ID {coaching_id} erfolgreich gelöscht.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Fehler beim Löschen von Coaching ID {coaching_id}: {e}")
        flash(f'Fehler beim Löschen von Coaching ID {coaching_id}.', 'danger')
    return redirect(url_for('admin.manage_coachings'))
