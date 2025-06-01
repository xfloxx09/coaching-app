# app/main_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_required, current_user
from app import db
from app.models import User, Team, TeamMember, Coaching
from app.forms import CoachingForm, ProjectLeaderNoteForm
from app.utils import role_required, ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_TEAMLEITER, ROLE_ABTEILUNGSLEITER
from sqlalchemy import desc, func, or_, and_
from datetime import datetime, timedelta, timezone
import sqlalchemy
from calendar import monthrange

bp = Blueprint('main', __name__)

# --- HILFSFUNKTIONEN FÜR DATENAGGREGATION ---

def get_month_name_german(month_number):
    months_german = {
        1: "Januar", 2: "Februar", 3: "März", 4: "April", 5: "Mai", 6: "Juni",
        7: "Juli", 8: "August", 9: "September", 10: "Oktober", 11: "November", 12: "Dezember"
    }
    return months_german.get(month_number, "")

def calculate_date_range(period_filter_str=None):
    now = datetime.now(timezone.utc)
    start_date, end_date = None, None
    if not period_filter_str or period_filter_str == 'all':
        return None, None
    if period_filter_str == '7days':
        start_date = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period_filter_str == '30days':
        start_date = (now - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period_filter_str == 'current_quarter':
        current_month_num = now.month; year = now.year
        if 1 <= current_month_num <= 3: start_date, end_date = datetime(year,1,1,0,0,0,tzinfo=timezone.utc), datetime(year,3,monthrange(year,3)[1],23,59,59,999999,tzinfo=timezone.utc)
        elif 4 <= current_month_num <= 6: start_date, end_date = datetime(year,4,1,0,0,0,tzinfo=timezone.utc), datetime(year,6,monthrange(year,6)[1],23,59,59,999999,tzinfo=timezone.utc)
        elif 7 <= current_month_num <= 9: start_date, end_date = datetime(year,7,1,0,0,0,tzinfo=timezone.utc), datetime(year,9,monthrange(year,9)[1],23,59,59,999999,tzinfo=timezone.utc)
        else: start_date, end_date = datetime(year,10,1,0,0,0,tzinfo=timezone.utc), datetime(year,12,monthrange(year,12)[1],23,59,59,999999,tzinfo=timezone.utc)
    elif period_filter_str == 'current_year':
        year = now.year; start_date = datetime(year,1,1,0,0,0,tzinfo=timezone.utc); end_date = datetime(year,12,monthrange(year,12)[1],23,59,59,999999,tzinfo=timezone.utc)
    elif '-' in period_filter_str and len(period_filter_str) == 7:
        try:
            year_str, month_str = period_filter_str.split('-'); year = int(year_str); month_int = int(month_str)
            if 1 <= month_int <= 12:
                start_date = datetime(year, month_int, 1, 0, 0, 0, tzinfo=timezone.utc)
                end_date = datetime(year, month_int, monthrange(year, month_int)[1], 23, 59, 59, 999999, tzinfo=timezone.utc)
        except ValueError: pass
    return start_date, end_date

def get_filtered_coachings_subquery(period_filter_str=None):
    coachings_base_q = db.session.query(Coaching.id.label("coaching_id_sq"), Coaching.team_member_id.label("team_member_id_sq"), Coaching.performance_mark.label("performance_mark_sq"), Coaching.time_spent.label("time_spent_sq"), Coaching.coaching_subject.label("coaching_subject_sq"))
    start_date, end_date = calculate_date_range(period_filter_str)
    if start_date: coachings_base_q = coachings_base_q.filter(Coaching.coaching_date >= start_date)
    if end_date: coachings_base_q = coachings_base_q.filter(Coaching.coaching_date <= end_date)
    return coachings_base_q.subquery('filtered_coachings_sq')

def get_performance_data_for_charts(period_filter_str=None, selected_team_id_str=None):
    filtered_coachings_sq = get_filtered_coachings_subquery(period_filter_str)
    query = db.session.query(Team.id.label('team_id'), Team.name.label('team_name'), func.coalesce(func.avg(filtered_coachings_sq.c.performance_mark_sq),0).label('avg_performance_mark'), func.coalesce(func.sum(filtered_coachings_sq.c.time_spent_sq),0).label('total_time_spent'), func.coalesce(func.count(filtered_coachings_sq.c.coaching_id_sq),0).label('coachings_done')).select_from(Team).outerjoin(TeamMember, Team.id == TeamMember.team_id).outerjoin(filtered_coachings_sq, TeamMember.id == filtered_coachings_sq.c.team_member_id_sq)
    if selected_team_id_str and selected_team_id_str.isdigit(): query = query.filter(Team.id == int(selected_team_id_str))
    results = query.group_by(Team.id, Team.name).order_by(Team.name).all()
    avg_perf_percent = [round(r.avg_performance_mark * 10, 2) if r.avg_performance_mark is not None else 0 for r in results]
    return {'labels':[r.team_name for r in results], 'avg_performance_values':avg_perf_percent, 'avg_time_spent_values':[round(r.total_time_spent/r.coachings_done,2) if r.coachings_done > 0 else 0 for r in results], 'coachings_done_values':[r.coachings_done for r in results]}

def get_coaching_subject_distribution(period_filter_str=None, selected_team_id_str=None):
    filtered_coachings_sq = get_filtered_coachings_subquery(period_filter_str)
    query = db.session.query(filtered_coachings_sq.c.coaching_subject_sq.label('coaching_subject'), func.count(filtered_coachings_sq.c.coaching_id_sq).label('count')).select_from(filtered_coachings_sq).filter(filtered_coachings_sq.c.coaching_subject_sq.isnot(None)).filter(filtered_coachings_sq.c.coaching_subject_sq != '')
    if selected_team_id_str and selected_team_id_str.isdigit(): query = query.join(TeamMember, filtered_coachings_sq.c.team_member_id_sq == TeamMember.id).filter(TeamMember.team_id == int(selected_team_id_str))
    results = query.group_by(filtered_coachings_sq.c.coaching_subject_sq).order_by(desc('count')).all()
    return {'labels':[r.coaching_subject for r in results if r.coaching_subject], 'values':[r.count for r in results if r.coaching_subject]}

@bp.route('/')
@bp.route('/index')
@login_required
def index():
    page = request.args.get('page', 1, type=int); period_arg = request.args.get('period','all'); team_arg = request.args.get('team',"all"); search_arg = request.args.get('search',default="",type=str).strip()
    query = Coaching.query.join(TeamMember,Coaching.team_member_id==TeamMember.id).join(User,Coaching.coach_id==User.id,isouter=True)
    start_dt, end_dt = calculate_date_range(period_arg)
    if start_dt: query = query.filter(Coaching.coaching_date >= start_dt)
    if end_dt: query = query.filter(Coaching.coaching_date <= end_dt)
    if current_user.role == ROLE_TEAMLEITER:
        if not current_user.team_id_if_leader: flash("Ihnen ist kein Team zugewiesen. Coaching-Liste leer.","warning"); query = query.filter(sqlalchemy.sql.false())
        else:
            tm_ids = [m.id for m in TeamMember.query.filter_by(team_id=current_user.team_id_if_leader).all()]
            if not tm_ids: query = query.filter(Coaching.coach_id == current_user.id)
            else: query = query.filter(or_(Coaching.team_member_id.in_(tm_ids), Coaching.coach_id == current_user.id))
    elif team_arg and team_arg.isdigit(): query = query.filter(TeamMember.team_id == int(team_arg))
    if search_arg: query = query.filter(or_(TeamMember.name.ilike(f"%{search_arg}%"), User.username.ilike(f"%{search_arg}%"), Coaching.coaching_subject.ilike(f"%{search_arg}%")))
    total_filtered = query.count()
    time_sum_obj = query.with_entities(func.sum(Coaching.time_spent)).scalar(); time_sum = time_sum_obj if time_sum_obj else 0
    time_display = f"{time_sum//60} Std. {time_sum%60} Min. ({time_sum} Min.)"
    coachings_page = query.order_by(desc(Coaching.coaching_date)).paginate(page=page,per_page=10,error_out=False)
    charts_perf_data = get_performance_data_for_charts(period_arg,team_arg); charts_subj_data = get_coaching_subject_distribution(period_arg,team_arg)
    all_teams = Team.query.order_by(Team.name).all()
    now = datetime.now(timezone.utc); curr_yr = now.year; prev_yr = curr_yr -1; months_opts = []
    for m_val in range(12,0,-1): months_opts.append({'value':f"{prev_yr}-{m_val:02d}",'text':f"{get_month_name_german(m_val)} {prev_yr}"})
    for m_val in range(now.month,0,-1): months_opts.append({'value':f"{curr_yr}-{m_val:02d}",'text':f"{get_month_name_german(m_val)} {curr_yr}"})
    return render_template('main/index.html',title='Coaching Tracker Dashboard',coachings_paginated=coachings_page,total_coachings=total_filtered,chart_labels=charts_perf_data['labels'],chart_avg_performance_mark_percentage=charts_perf_data['avg_performance_values'],chart_avg_time_spent=charts_perf_data['avg_time_spent_values'],chart_coachings_done=charts_perf_data['coachings_done_values'],subject_chart_labels=charts_subj_data['labels'],subject_chart_values=charts_subj_data['values'],all_teams_for_filter=all_teams,current_period_filter=period_arg,current_team_id_filter=team_arg,current_search_term=search_arg,total_filtered_coachings_count=total_filtered,time_coached_display=time_display,month_options=months_opts,config=current_app.config)

@bp.route('/team_view')
@login_required
@role_required([ROLE_TEAMLEITER, ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_ABTEILUNGSLEITER])
def team_view():
    team, team_coachings, team_performance, view_team_id = None, [], [], request.args.get('team_id',type=int)
    title_prefix = "Team Ansicht"
    if current_user.role == ROLE_TEAMLEITER and not view_team_id:
        if not current_user.team_id_if_leader: flash("Ihnen ist kein Team zugewiesen.","warning"); return redirect(url_for('main.index'))
        team = Team.query.get(current_user.team_id_if_leader); title_prefix = "Mein Team" if team else title_prefix
    elif view_team_id:
        if current_user.role not in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_ABTEILUNGSLEITER]: abort(403)
        team = Team.query.get(view_team_id)
    else:
        if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_ABTEILUNGSLEITER]: team = Team.query.first()
        else: abort(403)
    if not team: flash("Team nicht gefunden.","info"); all_teams_list = Team.query.order_by(Team.name).all() if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER,ROLE_QM,ROLE_SALESCOACH,ROLE_TRAINER,ROLE_ABTEILUNGSLEITER] else []; return render_template('main/team_view.html',title='Team Ansicht',team=None,all_teams_list=all_teams_list,config=current_app.config)
    if team:
        member_ids = [m.id for m in team.members]; team_coachings = Coaching.query.filter(Coaching.team_member_id.in_(member_ids)).order_by(desc(Coaching.coaching_date)).limit(20).all()
        for member in team.members:
            m_coachings = Coaching.query.filter_by(team_member_id=member.id).all()
            avg_score = sum(c.overall_score for c in m_coachings)/len(m_coachings) if m_coachings else 0
            total_time = sum(c.time_spent for c in m_coachings if c.time_spent)
            team_performance.append({'name':member.name,'avg_score':round(avg_score,2),'total_coachings':len(m_coachings),'total_coaching_time':total_time})
    all_teams_dd = Team.query.order_by(Team.name).all() if current_user.role in [ROLE_ADMIN,ROLE_PROJEKTLEITER,ROLE_QM,ROLE_SALESCOACH,ROLE_TRAINER,ROLE_ABTEILUNGSLEITER] else []
    return render_template('main/team_view.html',title=f"{title_prefix}: {team.name}" if team else title_prefix, team=team,team_coachings=team_coachings,team_members_performance=team_performance,all_teams_list=all_teams_dd,config=current_app.config)

@bp.route('/coaching/add', methods=['GET', 'POST'])
@login_required
@role_required([ROLE_TEAMLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_ADMIN]) # Only these roles can add
def add_coaching():
    user_team_id = current_user.team_id_if_leader if current_user.role == ROLE_TEAMLEITER else None
    form = CoachingForm(current_user_role=current_user.role, current_user_team_id=user_team_id)
    if form.validate_on_submit():
        try:
            coaching = Coaching(team_member_id=form.team_member_id.data,coach_id=current_user.id,coaching_style=form.coaching_style.data,tcap_id=form.tcap_id.data if form.coaching_style.data=='TCAP' and form.tcap_id.data else None,coaching_subject=form.coaching_subject.data,coach_notes=form.coach_notes.data if form.coach_notes.data else None,leitfaden_begruessung=form.leitfaden_begruessung.data,leitfaden_legitimation=form.leitfaden_legitimation.data,leitfaden_pka=form.leitfaden_pka.data,leitfaden_kek=form.leitfaden_kek.data,leitfaden_angebot=form.leitfaden_angebot.data,leitfaden_zusammenfassung=form.leitfaden_zusammenfassung.data,leitfaden_kzb=form.leitfaden_kzb.data,performance_mark=form.performance_mark.data,time_spent=form.time_spent.data)
            db.session.add(coaching); db.session.commit()
            flash('Coaching erfolgreich gespeichert!', 'success'); return redirect(url_for('main.index'))
        except Exception as e: db.session.rollback(); current_app.logger.error(f"Add coaching error: {e}"); flash(f'Fehler: {str(e)}', 'danger')
    elif request.method == 'POST':
        for field,errors in form.errors.items(): flash(f"Fehler '{form[field].label.text}': {'; '.join(errors)}", 'danger')
    tcap_js="document.addEventListener('DOMContentLoaded',function(){var s=document.getElementById('coaching_style'),t=document.getElementById('tcap_id_field'),i=document.getElementById('tcap_id');function o(){if(s&&t&&i)if(s.value==='TCAP'){t.style.display='';i.required=!0}else{t.style.display='none';i.required=!1;i.value=''}}s&&t&&i&&(s.addEventListener('change',o),o())});"
    return render_template('main/add_coaching.html', title='Coaching hinzufügen', form=form, tcap_js=tcap_js, is_edit_mode=False, config=current_app.config)

# NEW ROUTE FOR EDITING COACHING
@bp.route('/coaching/<int:coaching_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_coaching(coaching_id):
    coaching_to_edit = Coaching.query.get_or_404(coaching_id)

    if not (current_user.id == coaching_to_edit.coach_id or current_user.role == ROLE_ADMIN):
        flash('Sie haben keine Berechtigung, dieses Coaching zu bearbeiten.', 'danger')
        abort(403)

    form_user_role_for_dropdown = current_user.role
    form_user_team_id_for_dropdown = None
    if current_user.id == coaching_to_edit.coach_id and current_user.role == ROLE_TEAMLEITER:
        form_user_team_id_for_dropdown = current_user.team_id_if_leader
    elif current_user.role == ROLE_ADMIN:
        form_user_role_for_dropdown = ROLE_ADMIN # Ensures Admin sees all members in dropdown

    form = CoachingForm(obj=coaching_to_edit, current_user_role=form_user_role_for_dropdown, current_user_team_id=form_user_team_id_for_dropdown)

    if form.validate_on_submit():
        try:
            form.populate_obj(coaching_to_edit)
            if coaching_to_edit.coaching_style != 'TCAP':
                coaching_to_edit.tcap_id = None
            db.session.commit()
            flash('Coaching erfolgreich aktualisiert!', 'success')
            return redirect(request.args.get('next') or url_for('main.index'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Fehler beim Aktualisieren von Coaching ID {coaching_id}: {e}")
            flash(f'Fehler beim Aktualisieren des Coachings: {str(e)}', 'danger')
    
    if request.method == 'GET' or not form.validate_on_submit():
        generated_choices = []
        if form_user_role_for_dropdown == ROLE_TEAMLEITER and form_user_team_id_for_dropdown:
            team_members = TeamMember.query.filter_by(team_id=form_user_team_id_for_dropdown).order_by(TeamMember.name).all()
            for m in team_members: generated_choices.append((m.id, m.name))
        else: # Admin or other roles that should see all
            all_teams_for_choices = Team.query.order_by(Team.name).all()
            for team_obj_choice in all_teams_for_choices:
                members = TeamMember.query.filter_by(team_id=team_obj_choice.id).order_by(TeamMember.name).all()
                for m in members: generated_choices.append((m.id, f"{m.name} ({team_obj_choice.name})"))
        
        form.team_member_id.choices = generated_choices if generated_choices else []
        form.team_member_id.data = coaching_to_edit.team_member_id # Pre-select current member

    tcap_js_edit = "document.addEventListener('DOMContentLoaded',function(){var s=document.getElementById('coaching_style'),t=document.getElementById('tcap_id_field'),i=document.getElementById('tcap_id');function o(){if(s&&t&&i)if(s.value==='TCAP'){t.style.display='';i.required=!0}else{t.style.display='none';i.required=!1;}}s&&t&&i&&(s.addEventListener('change',o),o())});" # Removed i.value='' for edit
    
    return render_template('main/add_coaching.html',
                           title=f'Coaching ID {coaching_to_edit.id} Bearbeiten',
                           form=form,
                           is_edit_mode=True,
                           coaching_id_being_edited=coaching_to_edit.id, # For form action
                           tcap_js=tcap_js_edit,
                           config=current_app.config)


@bp.route('/coaching_review_dashboard', methods=['GET', 'POST'])
@login_required
@role_required([ROLE_PROJEKTLEITER, ROLE_QM, ROLE_ABTEILUNGSLEITER])
def pl_qm_dashboard():
    page = request.args.get('page', 1, type=int)
    coachings_paginated = Coaching.query.order_by(desc(Coaching.coaching_date)).paginate(page=page, per_page=10, error_out=False)
    note_form = ProjectLeaderNoteForm()
    title = "Notizen Dashboard"
    if current_user.role == ROLE_QM: title = "Quality Coach Dashboard"
    elif current_user.role == ROLE_PROJEKTLEITER: title = "Projektleiter Dashboard"
    elif current_user.role == ROLE_ABTEILUNGSLEITER: title = "Abteilungsleiter Dashboard"
    
    if request.method == 'POST' and 'submit_note' in request.form:
        form_val = ProjectLeaderNoteForm(request.form); coaching_id_str = request.form.get('coaching_id')
        if not coaching_id_str or not coaching_id_str.isdigit(): flash("Gültige Coaching-ID fehlt.", 'danger')
        elif form_val.validate():
            try:
                coaching = Coaching.query.get_or_404(int(coaching_id_str))
                coaching.project_leader_notes = form_val.notes.data; db.session.commit()
                flash(f'Notiz für Coaching ID {coaching_id_str} gespeichert.', 'success')
            except Exception as e: db.session.rollback(); current_app.logger.error(f"Note save error: {e}"); flash('Fehler Notizspeicherung.', 'danger')
        else:
            for f, errs in form_val.errors.items(): flash(f"Validierungsfehler '{form_val[f].label.text}': {'; '.join(errs)}", 'danger')
        return redirect(url_for('main.pl_qm_dashboard', page=request.args.get('page',1,type=int)))

    all_teams_data = []
    for team_obj_stat in Team.query.all():
        stats = db.session.query(func.coalesce(func.avg(Coaching.performance_mark*10.0),0).label('avg_perf'), func.coalesce(func.sum(Coaching.time_spent),0).label('total_time'), func.coalesce(func.count(Coaching.id),0).label('num_coachings')).join(TeamMember, Coaching.team_member_id == TeamMember.id).filter(TeamMember.team_id == team_obj_stat.id).first()
        all_teams_data.append({'id':team_obj_stat.id,'name':team_obj_stat.name,'num_coachings':stats.num_coachings if stats else 0,'avg_score':round(stats.avg_perf,2) if stats else 0,'total_time':stats.total_time if stats else 0})
    sorted_teams_data = sorted(all_teams_data,key=lambda x:(x.get('avg_score',0),x.get('num_coachings',0)),reverse=True)
    top_3 = sorted_teams_data[:3]
    teams_with_c = [t for t in all_teams_data if t.get('num_coachings',0) > 0]
    flop_3 = sorted(teams_with_c,key=lambda x:(x.get('avg_score',0),-x.get('num_coachings',0)))[:3] if teams_with_c else []
    return render_template('main/projektleiter_dashboard.html',title=title,coachings_paginated=coachings_paginated,note_form=note_form,top_3_teams=top_3,flop_3_teams=flop_3,config=current_app.config)
