# app/admin.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from sqlalchemy import desc, or_
from app import db
from app.models import User, Team, TeamMember, Coaching # Ensure Coaching is imported
from app.forms import RegistrationForm, TeamForm, TeamMemberForm, CoachingForm # Import CoachingForm
from app.utils import role_required, ROLE_ADMIN, ROLE_TEAMLEITER
# Import helpers from main_routes (ensure main_routes.py has these accessible or define them here)
from app.main_routes import calculate_date_range, get_month_name_german
from datetime import datetime, timezone # For month_options generation

bp = Blueprint('admin', __name__)

@bp.route('/')
@login_required
@role_required(ROLE_ADMIN)
def panel():
    users = User.query.order_by(User.username).all()
    teams = Team.query.order_by(Team.name).all()
    team_members = TeamMember.query.order_by(TeamMember.name).all()
    return render_template('admin/admin_panel.html', title='Admin Panel',
                           users=users, teams=teams, team_members=team_members, config=current_app.config)

# --- User Management ---
@bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def create_user():
    form = RegistrationForm()
    active_teams = Team.query.order_by(Team.name).all()
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

    if not form.password.data: # If a new password isn't being set
        form.password.validators = []
        form.password2.validators = [] # Also remove for password2 if password is empty
    elif not form.password2.data and form.password.data: # If password is set but not password2
         # Keep original validators for password, but password2 will fail EqualTo if empty and required
         pass


    active_teams = Team.query.order_by(Team.name).all()
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
            
            if form.password.data: # Only set password if new one is provided
                user_to_edit.set_password(form.password.data)
            
            db.session.commit()

            # Team leader assignment logic
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
                # If user is no longer TL OR is TL but no longer assigned to THAT specific team
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
    else: # POST but not validate_on_submit
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Fehler im Feld '{form[field].label.text if hasattr(form[field], 'label') else field}': {error}", 'danger')
    
    return render_template('admin/edit_user.html', title='Benutzer bearbeiten', form=form, user=user_to_edit, config=current_app.config)

@bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.username == 'admin' or user.id == current_user.id: # Basic protection
        flash('Dieser Benutzer kann nicht gelöscht werden.', 'danger')
        return redirect(url_for('admin.panel'))
    
    try:
        if user.role == ROLE_TEAMLEITER and user.team_id_if_leader:
            team_led = Team.query.get(user.team_id_if_leader)
            if team_led and team_led.team_leader_id == user.id:
                team_led.team_leader_id = None
        
        # Handle coachings led by this user: set coach_id to NULL (if allowed by DB schema)
        # or prevent deletion if coachings exist. Here we attempt to nullify.
        # Ensure your Coaching model's coach_id allows NULL or this will fail.
        # Alternatively, delete related coachings or reassign them.
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
                else: # Selected user not a teamleiter or not found
                    flash('Ausgewählter Benutzer ist kein Teamleiter oder existiert nicht. Team ohne Leiter erstellt.', 'warning')
            
            flash('Team erfolgreich erstellt!', 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Fehler beim Erstellen des Teams: {e}")
            flash(f'Fehler beim Erstellen des Teams: {str(e)}', 'danger')
    return render_template('admin/create_team.html', title='Team erstellen', form=form, config=current_app.config)

@bp.route('/teams/edit/<int:team_id_param>', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def edit_team(team_id_param):
    team_to_edit = Team.query.get_or_404(team_id_param)
    form = TeamForm(obj=team_to_edit)
    
    if form.validate_on_submit():
        try:
            team_to_edit.name = form.name.data
            new_leader_id = int(form.team_leader_id.data) if form.team_leader_id.data and str(form.team_leader_id.data).isdigit() else 0
            old_leader_id = team_to_edit.team_leader_id

            if new_leader_id != old_leader_id:
                if old_leader_id:
                    old_leader = User.query.get(old_leader_id)
                    if old_leader:
                        old_leader.team_id_if_leader = None
                
                if new_leader_id != 0:
                    new_leader = User.query.get(new_leader_id)
                    if new_leader and new_leader.role == ROLE_TEAMLEITER:
                        if new_leader.team_id_if_leader and new_leader.team_id_if_leader != team_to_edit.id:
                            previous_team_of_new_leader = Team.query.get(new_leader.team_id_if_leader)
                            if previous_team_of_new_leader:
                                previous_team_of_new_leader.team_leader_id = None
                        team_to_edit.team_leader_id = new_leader.id
                        new_leader.team_id_if_leader = team_to_edit.id
                    else:
                        flash('Neuer ausgewählter Benutzer ist kein Teamleiter oder existiert nicht. Teamleiter nicht geändert.', 'warning')
                        team_to_edit.team_leader_id = old_leader_id # Revert if new leader is invalid
                else:
                    team_to_edit.team_leader_id = None
            
            db.session.commit()
            flash('Team erfolgreich aktualisiert!', 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Fehler beim Bearbeiten des Teams {team_id_param}: {e}")
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
    if team.members.count() > 0:
        flash('Team kann nicht gelöscht werden, da ihm noch Mitglieder zugeordnet sind.', 'danger')
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
    # Check if any actual teams exist for assignment
    if not any(choice[0] for choice in form.team_id.choices if choice[0] != "" and choice[0] is not None): # Check if a valid team ID exists
        flash("Bitte erstellen Sie zuerst mindestens ein Team, bevor Sie Mitglieder hinzufügen.", "warning")
        return redirect(url_for('admin.create_team') if Team.query.count() == 0 else url_for('admin.panel'))

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

    if form.validate_on_submit():
        try:
            member.name = form.name.data
            member.team_id = form.team_id.data
            db.session.commit()
            flash('Teammitglied erfolgreich aktualisiert!', 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Fehler beim Bearbeiten des Teammitglieds {member_id}: {e}")
            flash(f'Fehler beim Bearbeiten des Teammitglieds: {str(e)}', 'danger')
    elif request.method == 'GET':
        form.team_id.data = member.team_id

    return render_template('admin/edit_team_member.html', title='Teammitglied bearbeiten', form=form, member=member, config=current_app.config)

@bp.route('/teammembers/delete/<int:member_id>', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def delete_team_member(member_id):
    member = TeamMember.query.get_or_404(member_id)
    if member.coachings_received.count() > 0: # coachings_received is the backref from Coaching to TeamMember
        flash('Teammitglied kann nicht gelöscht werden, da bereits Coachings für dieses Mitglied existieren.', 'danger')
        return redirect(url_for('admin.panel'))
    try:
        db.session.delete(member)
        db.session.commit()
        flash('Teammitglied gelöscht.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Fehler beim Löschen von Teammitglied ID {member_id}: {e}")
        flash('Fehler beim Löschen des Teammitglieds.', 'danger')
    return redirect(url_for('admin.panel'))


# --- NEW: Coaching Management ---
@bp.route('/manage_coachings', methods=['GET', 'POST'])
@login_required
@role_required([ROLE_ADMIN])
def manage_coachings():
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
                    deleted_count = Coaching.query.filter(Coaching.id.in_(coaching_ids_to_delete_int)).delete(synchronize_session='fetch') # Changed to 'fetch'
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

    all_teams = Team.query.order_by(Team.name).all()
    all_team_members = TeamMember.query.order_by(TeamMember.name).all()
    all_coaches = User.query.filter(User.coachings_done.any()).distinct().order_by(User.username).all()

    now_dt = datetime.now(timezone.utc)
    current_year_val = now_dt.year
    previous_year_val = current_year_val - 1
    month_options_for_filter = [] # Renamed to avoid conflict
    for m_num in range(12, 0, -1):
        month_options_for_filter.append({'value': f"{previous_year_val}-{m_num:02d}", 'text': f"{get_month_name_german(m_num)} {previous_year_val}"})
    # Only add current year months up to the current month if you want to avoid future months
    for m_num in range(now_dt.month, 0, -1): 
        month_options_for_filter.append({'value': f"{current_year_val}-{m_num:02d}", 'text': f"{get_month_name_german(m_num)} {current_year_val}"})
    # If you want all months of current year:
    # for m_num in range(12, 0, -1):
    #    month_options_for_filter.append({'value': f"{current_year_val}-{m_num:02d}", 'text': f"{get_month_name_german(m_num)} {current_year_val}"})


    return render_template('admin/manage_coachings.html', 
                           title='Coachings Verwalten',
                           coachings_paginated=coachings_paginated,
                           all_teams=all_teams,
                           all_team_members=all_team_members,
                           all_coaches=all_coaches,
                           month_options=month_options_for_filter, # Use renamed variable
                           current_period_filter=period_filter_arg,
                           current_team_id_filter=team_filter_arg,
                           current_teammember_id_filter=team_member_filter_arg,
                           current_coach_id_filter=coach_filter_arg,
                           current_search_term=search_term,
                           config=current_app.config)

@bp.route('/coaching/<int:coaching_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required([ROLE_ADMIN])
def edit_coaching_entry(coaching_id):
    coaching_to_edit = Coaching.query.get_or_404(coaching_id)
    # We need to determine the current_user_role and team_id for the CoachingForm logic
    # Since this is admin, they can edit for anyone.
    # We can pass None, or determine if the original coach was a teamleiter to pre-select their team members.
    # For simplicity, let's assume admin can see all team members.
    form = CoachingForm(obj=coaching_to_edit, current_user_role=ROLE_ADMIN, current_user_team_id=None)

    if form.validate_on_submit():
        try:
            # Populate all fields from the form to the coaching_to_edit object
            form.populate_obj(coaching_to_edit) # WTForms helper to populate object from form
            # Explicitly set coach_id if you want to allow changing the coach (form needs coach_id field)
            # coaching_to_edit.coach_id = form.coach_id.data 
            # Ensure date is handled if it's editable (CoachingForm doesn't have coaching_date field by default)
            
            db.session.commit()
            flash(f'Coaching ID {coaching_id} erfolgreich aktualisiert!', 'success')
            return redirect(url_for('admin.manage_coachings'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating coaching ID {coaching_id}: {e}")
            flash(f'Fehler beim Aktualisieren von Coaching ID {coaching_id}.', 'danger')
    elif request.method == 'GET':
        # Form is already populated by obj=coaching_to_edit in its instantiation
        pass # team_member_id choices are handled in CoachingForm.__init__

    # Re-fetch choices if they were not set correctly due to context or if it's a GET
    # This is mainly for the team_member_id field in CoachingForm
    if request.method == 'GET' or not form.validate_on_submit(): # Also on failed POST
        # Logic from CoachingForm.__init__ to populate team_member_id choices
        generated_choices = []
        all_teams = Team.query.order_by(Team.name).all()
        for team_obj_form in all_teams: # Renamed to avoid conflict
            members = TeamMember.query.filter_by(team_id=team_obj_form.id).order_by(TeamMember.name).all()
            for m in members:
                generated_choices.append((m.id, f"{m.name} ({team_obj_form.name})"))
        
        if not generated_choices:
            form.team_member_id.choices = []
        else:
            form.team_member_id.choices = generated_choices
        
        # Ensure current value is selected
        form.team_member_id.data = coaching_to_edit.team_member_id


    tcap_js_for_edit = """ 
    document.addEventListener('DOMContentLoaded', function() {
        var styleSelect = document.getElementById('coaching_style');
        var tcapIdField = document.getElementById('tcap_id_field');
        function toggleTcapField() {
            if (styleSelect && tcapIdField) { 
                if (styleSelect.value === 'TCAP') {
                    tcapIdField.style.display = '';
                    if(document.getElementById('tcap_id')) document.getElementById('tcap_id').required = true;
                } else {
                    tcapIdField.style.display = 'none';
                    if(document.getElementById('tcap_id')) {
                        // document.getElementById('tcap_id').value = ''; // Don't clear on edit unless style changes
                        document.getElementById('tcap_id').required = false;
                    }
                }
            }
        }
        if(styleSelect && tcapIdField) {
            styleSelect.addEventListener('change', toggleTcapField);
            toggleTcapField(); // Call on load to set initial state
        }
    });
    """
    # You would typically render a specific edit_coaching.html template
    return render_template('main/add_coaching.html', # REUSING add_coaching for now
                            title=f'Coaching ID {coaching_id} bearbeiten', 
                            form=form, 
                            is_edit_mode=True, # Flag for template if needed
                            coaching=coaching_to_edit,
                            tcap_js=tcap_js_for_edit, # Pass the JS
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
    # Redirect to manage_coachings, preserving filters if possible (requires passing them)
    # For simplicity now, just redirecting without preserving filters from single delete.
    return redirect(url_for('admin.manage_coachings'))
