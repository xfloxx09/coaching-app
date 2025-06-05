# app/admin.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from sqlalchemy import desc, or_, func 
from app import db
from app.models import User, Team, TeamMember, Coaching
from app.forms import RegistrationForm, TeamForm, TeamMemberForm, CoachingForm 
from app.utils import (role_required, ROLE_ADMIN, ROLE_TEAMLEITER, ROLE_PROJEKTLEITER, 
                       ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_ABTEILUNGSLEITER, ROLE_TEAMMITGLIED)
from app.main_routes import calculate_date_range, get_month_name_german # Ensure these exist and are correct
from datetime import datetime, timezone

bp = Blueprint('admin', __name__)

@bp.route('/')
@login_required
@role_required(ROLE_ADMIN)
def panel():
    users = User.query.order_by(User.username).all()
    teams = Team.query.order_by(Team.name).all()
    # Display all team members, including those with team_id=None (archived)
    team_members = TeamMember.query.order_by(TeamMember.name).all() 
    return render_template('admin/admin_panel.html', title='Admin Panel',
                           users=users, teams=teams, team_members=team_members, config=current_app.config)

# --- User Management ---
# Your existing User management routes (create_user, edit_user, delete_user)
# should largely remain the same as your provided file.
# The key is that RegistrationForm and TeamForm __init__ methods correctly populate choices.
# I'll include them here with minor adjustments for consistency if needed.

@bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def create_user():
    form = RegistrationForm() # team_id_for_leader choices set in __init__
    if form.validate_on_submit():
        try:
            user = User(username=form.username.data, email=form.email.data, role=form.role.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit() # Commit user to get ID

            selected_team_id_for_leader = form.team_id_for_leader.data
            if user.role == ROLE_TEAMLEITER and selected_team_id_for_leader and int(selected_team_id_for_leader) != 0:
                team_to_assign = Team.query.get(int(selected_team_id_for_leader))
                if team_to_assign:
                    if team_to_assign.team_leader_id and team_to_assign.team_leader_id != user.id:
                        old_leader = User.query.get(team_to_assign.team_leader_id)
                        if old_leader: old_leader.team_id_if_leader = None 
                    user.team_id_if_leader = team_to_assign.id
                    team_to_assign.team_leader_id = user.id
            db.session.commit()
            flash('Benutzer erfolgreich erstellt!', 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback(); current_app.logger.error(f"User Create Error: {e}")
            flash(f'Fehler: {str(e)}', 'danger')
    elif request.method == 'POST':
        for field, errors in form.errors.items():
            for error in errors: flash(f"Fehler '{form[field].label.text}': {error}", 'danger')
    return render_template('admin/create_user.html', title='Benutzer erstellen', form=form, config=current_app.config)

@bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def edit_user(user_id):
    user_to_edit = User.query.get_or_404(user_id)
    form = RegistrationForm(obj=user_to_edit, original_username=user_to_edit.username)
    if not form.password.data: form.password.validators, form.password2.validators = [], []
    
    if form.validate_on_submit():
        try:
            original_team_id_if_leader = user_to_edit.team_id_if_leader
            new_role = form.role.data
            
            user_to_edit.username = form.username.data
            user_to_edit.email = form.email.data

            if user_to_edit.role == ROLE_TEAMLEITER and (new_role != ROLE_TEAMLEITER or (form.team_id_for_leader.data and int(form.team_id_for_leader.data) != original_team_id_if_leader)):
                if original_team_id_if_leader:
                    old_team = Team.query.get(original_team_id_if_leader)
                    if old_team and old_team.team_leader_id == user_to_edit.id: old_team.team_leader_id = None
            
            user_to_edit.role = new_role
            
            if user_to_edit.role == ROLE_TEAMLEITER:
                new_assigned_team_id = int(form.team_id_for_leader.data) if form.team_id_for_leader.data else 0
                if new_assigned_team_id != 0:
                    team_to_assign = Team.query.get(new_assigned_team_id)
                    if team_to_assign:
                        if team_to_assign.team_leader_id and team_to_assign.team_leader_id != user_to_edit.id:
                            other_leader = User.query.get(team_to_assign.team_leader_id)
                            if other_leader: other_leader.team_id_if_leader = None
                        team_to_assign.team_leader_id = user_to_edit.id
                        user_to_edit.team_id_if_leader = team_to_assign.id
                    else: user_to_edit.team_id_if_leader = None # Team not found
                else: user_to_edit.team_id_if_leader = None # "Kein Team" selected
            else: user_to_edit.team_id_if_leader = None

            if form.password.data: user_to_edit.set_password(form.password.data)
            db.session.commit()
            flash('Benutzer erfolgreich aktualisiert!', 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback(); current_app.logger.error(f"User Edit Error {user_id}: {e}")
            flash(f'Fehler: {str(e)}', 'danger')
    elif request.method == 'GET':
        form.username.data = user_to_edit.username # Ensure prefill
        form.email.data = user_to_edit.email
        form.role.data = user_to_edit.role
        form.team_id_for_leader.data = user_to_edit.team_id_if_leader if user_to_edit.team_id_if_leader else 0
    else: # POST with validation errors
        for field, errors in form.errors.items():
            for error in errors: flash(f"Fehler '{form[field].label.text}': {error}", 'danger')
    return render_template('admin/edit_user.html', title='Benutzer bearbeiten', form=form, user=user_to_edit, config=current_app.config)

@bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def delete_user(user_id):
    user_to_delete = User.query.get_or_404(user_id)
    if user_to_delete.username == 'admin' or user_to_delete.id == current_user.id:
        flash('Dieser Benutzer kann nicht gelöscht werden.', 'danger')
        return redirect(url_for('admin.panel'))
    try:
        if user_to_delete.role == ROLE_TEAMLEITER and user_to_delete.team_id_if_leader:
            team_led = Team.query.get(user_to_delete.team_id_if_leader)
            if team_led and team_led.team_leader_id == user_to_delete.id: team_led.team_leader_id = None
        
        # Set coach_id to NULL for coachings. Requires Coaching.coach_id to be nullable.
        Coaching.query.filter_by(coach_id=user_id).update({"coach_id": None}) 
        db.session.delete(user_to_delete)
        db.session.commit()
        flash('Benutzer gelöscht.', 'success')
    except Exception as e:
        db.session.rollback(); current_app.logger.error(f"User Delete Error {user_id}: {e}")
        flash(f'Fehler beim Löschen. Es könnten noch Daten verknüpft sein.', 'danger')
    return redirect(url_for('admin.panel'))

# --- Team Management ---
# create_team, edit_team, delete_team routes largely same as your provided file.
# Key is that TeamForm correctly populates leader choices.
@bp.route('/teams/create', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def create_team():
    form = TeamForm()
    if form.validate_on_submit():
        try:
            team = Team(name=form.name.data)
            db.session.add(team); db.session.commit()
            selected_leader_id = form.team_leader_id.data
            if selected_leader_id and int(selected_leader_id) != 0:
                leader = User.query.get(int(selected_leader_id))
                if leader and leader.role == ROLE_TEAMLEITER:
                    if leader.team_id_if_leader and leader.team_id_if_leader != team.id:
                        old_team = Team.query.get(leader.team_id_if_leader)
                        if old_team: old_team.team_leader_id = None
                    team.team_leader_id = leader.id
                    leader.team_id_if_leader = team.id
                else: flash('Gewählter User ist kein Teamleiter. Team ohne Leiter erstellt.', 'warning')
            db.session.commit()
            flash('Team erfolgreich erstellt!', 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback(); current_app.logger.error(f"Team Create Error: {e}"); flash(f'Fehler: {str(e)}', 'danger')
    return render_template('admin/create_team.html', title='Team erstellen', form=form, config=current_app.config)

@bp.route('/teams/edit/<int:team_id>', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def edit_team(team_id):
    team_to_edit = Team.query.get_or_404(team_id)
    form = TeamForm(obj=team_to_edit)
    if form.validate_on_submit():
        try:
            team_to_edit.name = form.name.data
            new_leader_id = int(form.team_leader_id.data) if form.team_leader_id.data else 0
            current_leader_id = team_to_edit.team_leader_id
            if new_leader_id != (current_leader_id if current_leader_id else 0):
                if current_leader_id:
                    old_leader = User.query.get(current_leader_id)
                    if old_leader: old_leader.team_id_if_leader = None
                if new_leader_id != 0:
                    new_leader = User.query.get(new_leader_id)
                    if new_leader and new_leader.role == ROLE_TEAMLEITER:
                        if new_leader.team_id_if_leader and new_leader.team_id_if_leader != team_to_edit.id:
                            other_team = Team.query.get(new_leader.team_id_if_leader)
                            if other_team: other_team.team_leader_id = None
                        team_to_edit.team_leader_id = new_leader.id
                        new_leader.team_id_if_leader = team_to_edit.id
                    else: flash('Neuer Leiter ist kein Teamleiter. Nicht geändert.', 'warning'); team_to_edit.team_leader_id = None
                else: team_to_edit.team_leader_id = None
            db.session.commit()
            flash('Team erfolgreich aktualisiert!', 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback(); current_app.logger.error(f"Team Edit Error {team_id}: {e}"); flash(f'Fehler: {str(e)}', 'danger')
    elif request.method == 'GET':
        form.name.data = team_to_edit.name
        form.team_leader_id.data = team_to_edit.team_leader_id if team_to_edit.team_leader_id else 0
    return render_template('admin/edit_team.html', title='Team bearbeiten', form=form, team=team_to_edit, config=current_app.config)

@bp.route('/teams/delete/<int:team_id>', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def delete_team(team_id):
    team_to_delete = Team.query.get_or_404(team_id)
    # Check for ANY members (active or inactive) whose team_id points to this team
    if TeamMember.query.filter_by(team_id=team_id).count() > 0:
        flash('Team kann nicht gelöscht werden, da ihm noch Mitglieder (aktiv oder archiviert) zugewiesen sind. Bitte Mitglieder zuerst einem anderen Team oder "Kein Team" zuweisen.', 'danger')
        return redirect(url_for('admin.panel'))
    try:
        if team_to_delete.team_leader: team_to_delete.team_leader.team_id_if_leader = None
        db.session.delete(team_to_delete); db.session.commit()
        flash('Team gelöscht.', 'success')
    except Exception as e:
        db.session.rollback(); current_app.logger.error(f"Team Delete Error {team_id}: {e}"); flash(f'Fehler: {str(e)}', 'danger')
    return redirect(url_for('admin.panel'))


# --- Team Member Management (Updated for team_id = None as "archived") ---
@bp.route('/teammembers/create', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def create_team_member():
    form = TeamMemberForm() # Choices set in __init__
    if form.validate_on_submit():
        try:
            member_name = form.name.data
            # If form.team_id.data is 0 (our "Kein Team" option), set actual_team_id to None
            actual_team_id = form.team_id.data if form.team_id.data != 0 else None
            
            new_member = TeamMember(name=member_name, team_id=actual_team_id)
            db.session.add(new_member)
            db.session.commit()
            flash_message = f'Teammitglied "{member_name}" erfolgreich erstellt.'
            if actual_team_id is None:
                flash_message += ' Mitglied ist keinem Team zugewiesen (archiviert).'
            flash(flash_message, 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback(); current_app.logger.error(f"TM Create Error: {e}"); flash(f'Fehler: {str(e)}', 'danger')
    elif request.method == 'POST': # Validation errors
        for field, errors in form.errors.items():
            for error in errors: flash(f"Fehler '{form[field].label.text}': {error}", 'danger')
    return render_template('admin/create_team_member.html', title='Teammitglied erstellen', form=form, config=current_app.config)

@bp.route('/teammembers/edit/<int:member_id>', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def edit_team_member(member_id):
    member_to_edit = TeamMember.query.get_or_404(member_id)
    form = TeamMemberForm(obj=member_to_edit) # Populates form
    if form.validate_on_submit():
        try:
            member_to_edit.name = form.name.data
            actual_team_id = form.team_id.data if form.team_id.data != 0 else None
            member_to_edit.team_id = actual_team_id
            db.session.commit()
            flash_message = f'Teammitglied "{member_to_edit.name}" erfolgreich aktualisiert.'
            if actual_team_id is None:
                flash_message += ' Mitglied ist nun keinem Team mehr zugewiesen (archiviert).'
            flash(flash_message, 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback(); current_app.logger.error(f"TM Edit Error {member_id}: {e}"); flash(f'Fehler: {str(e)}', 'danger')
    elif request.method == 'GET':
        form.name.data = member_to_edit.name # Ensure name is pre-filled
        form.team_id.data = member_to_edit.team_id if member_to_edit.team_id is not None else 0
    return render_template('admin/edit_team_member.html', title='Teammitglied bearbeiten', form=form, member=member_to_edit, config=current_app.config)

@bp.route('/teammembers/delete/<int:member_id>', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def delete_team_member(member_id):
    member_to_delete = TeamMember.query.get_or_404(member_id)
    if member_to_delete.all_coachings_for_this_member_record.count() > 0: # Check relationship
        flash('Teammitglied kann nicht gelöscht werden, da Coachings existieren. Weisen Sie stattdessen "Kein Team" zu, um das Mitglied zu archivieren.', 'danger')
        return redirect(url_for('admin.panel'))
    try:
        db.session.delete(member_to_delete); db.session.commit()
        flash('Teammitglied (ohne Coachings) gelöscht.', 'success')
    except Exception as e:
        db.session.rollback(); current_app.logger.error(f"TM Delete Error {member_id}: {e}"); flash(f'Fehler: {str(e)}', 'danger')
    return redirect(url_for('admin.panel'))

# --- Coaching Management (Admin) ---
# Uses existing routes from your provided file, but logic within CoachingForm
# and data display in templates will implicitly handle the "archived" member state.
# manage_coachings, edit_coaching_entry, delete_coaching_entry will use the same
# route names as your provided file. The 'by_admin' suffix can be removed if these are the primary admin routes for these actions.
# If you had 'edit_coaching_entry' and now want 'edit_coaching_entry_by_admin', ensure the old one is removed or updated.

@bp.route('/manage_coachings', methods=['GET', 'POST'])
@login_required
@role_required([ROLE_ADMIN])
def manage_coachings():
    page = request.args.get('page', 1, type=int)
    period_arg = request.args.get('period', 'all')
    team_filter_arg = request.args.get('team', 'all') # Filters by member's CURRENT team
    member_filter_arg = request.args.get('teammember', 'all')
    coach_filter_arg = request.args.get('coach', 'all')
    search_term = request.args.get('search', default="", type=str).strip()

    # Base query, joins to get names for display and filtering
    query = Coaching.query \
        .join(TeamMember, Coaching.team_member_id == TeamMember.id) \
        .outerjoin(User, Coaching.coach_id == User.id) \
        .outerjoin(Team, TeamMember.team_id == Team.id) # TeamMember's current team

    start_date, end_date = calculate_date_range(period_arg)
    if start_date: query = query.filter(Coaching.coaching_date >= start_date)
    if end_date: query = query.filter(Coaching.coaching_date <= end_date)

    if team_filter_arg.isdigit(): query = query.filter(TeamMember.team_id == int(team_filter_arg))
    if member_filter_arg.isdigit(): query = query.filter(Coaching.team_member_id == int(member_filter_arg))
    if coach_filter_arg.isdigit(): query = query.filter(Coaching.coach_id == int(coach_filter_arg))
    
    if search_term: # Search logic as per your file
        s = f"%{search_term}%"
        query = query.filter(or_(TeamMember.name.ilike(s), User.username.ilike(s), Team.name.ilike(s), Coaching.coaching_subject.ilike(s), Coaching.coaching_style.ilike(s), Coaching.tcap_id.ilike(s)))
    
    if request.method == 'POST' and 'delete_selected' in request.form: # Delete logic as per your file
        ids = request.form.getlist('coaching_ids')
        if ids:
            try:
                count = Coaching.query.filter(Coaching.id.in_([int(id) for id in ids])).delete(synchronize_session='fetch')
                db.session.commit(); flash(f'{count} Coaching(s) gelöscht.', 'success')
            except Exception as e: db.session.rollback(); flash(f'Fehler: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_coachings', page=page, period=period_arg, team=team_filter_arg, teammember=member_filter_arg, coach=coach_filter_arg, search=search_term))

    coachings_paginated = query.order_by(desc(Coaching.coaching_date)).paginate(page=page, per_page=15, error_out=False)
    # Dropdown data fetching as per your file
    all_teams_dd = Team.query.order_by(Team.name).all()
    all_members_dd = TeamMember.query.order_by(TeamMember.name).all() # Show all, including archived, for filtering history
    all_coaches_dd = User.query.filter(User.coachings_done.any()).distinct().order_by(User.username).all()
    month_opts_dd = [] # Month options logic as per your file
    now = datetime.now(timezone.utc)
    for yr_off in range(2):
        yr = now.year - yr_off
        m_start = 12 if yr_off > 0 else now.month
        for m in range(m_start, 0, -1): month_opts_dd.append({'value': f"{yr}-{m:02d}", 'text': f"{get_month_name_german(m)} {yr}"})

    return render_template('admin/manage_coachings.html', title='Coachings Verwalten',
                           coachings_paginated=coachings_paginated, all_teams=all_teams_dd,
                           all_team_members=all_members_dd, all_coaches=all_coaches_dd, month_options=month_opts_dd,
                           current_period_filter=period_arg, current_team_id_filter=team_filter_arg,
                           current_teammember_id_filter=member_filter_arg, current_coach_id_filter=coach_filter_arg,
                           current_search_term=search_term, config=current_app.config)

@bp.route('/coaching/<int:coaching_id>/edit_admin', methods=['GET', 'POST']) # Consistent naming
@login_required
@role_required(ROLE_ADMIN)
def edit_coaching_admin(coaching_id): # Consistent naming
    coaching = Coaching.query.get_or_404(coaching_id)
    form = CoachingForm(obj=coaching, current_user_role=ROLE_ADMIN, current_user_team_id=None) # Admin can see all assignable members
    if form.validate_on_submit():
        try:
            form.populate_obj(coaching)
            # team_member_id is validated by CoachingForm to be assigned to a team
            if coaching.coaching_style != 'TCAP': coaching.tcap_id = None
            db.session.commit(); flash(f'Coaching ID {coaching_id} aktualisiert.', 'success')
            return redirect(url_for('admin.manage_coachings'))
        except Exception as e:
            db.session.rollback(); current_app.logger.error(f"Admin Edit Coaching Error {coaching_id}: {e}"); flash(f'Fehler: {str(e)}', 'danger')
    
    if request.method == 'GET' or not form.validate_on_submit(): # Repopulate form on GET or failed POST
        # Choices are set by CoachingForm.__init__. We just need to set the current data for GET.
        if request.method == 'GET':
            form.team_member_id.data = coaching.team_member_id
    
    tcap_js_script = "/* ... Your TCAP JS for add_coaching.html ... */" # Your TCAP JS from main_routes.get_tcap_js() or similar
    return render_template('main/add_coaching.html', title=f'Admin Edit: Coaching ID {coaching_id}',
                           form=form, is_edit_mode=True, coaching=coaching,
                           tcap_js=tcap_js_script, config=current_app.config)

@bp.route('/coaching/<int:coaching_id>/delete_admin', methods=['POST']) # Consistent naming
@login_required
@role_required(ROLE_ADMIN)
def delete_coaching_admin(coaching_id): # Consistent naming
    coaching = Coaching.query.get_or_404(coaching_id)
    try:
        db.session.delete(coaching); db.session.commit()
        flash(f'Coaching ID {coaching_id} gelöscht.', 'success')
    except Exception as e:
        db.session.rollback(); current_app.logger.error(f"Admin Delete Coaching Error {coaching_id}: {e}"); flash(f'Fehler: {str(e)}', 'danger')
    return redirect(url_for('admin.manage_coachings'))
