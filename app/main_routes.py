# app/main_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app, jsonify # Added jsonify
from flask_login import login_required, current_user
from app import db
from app.models import User, Team, TeamMember, Coaching # Ensure all are imported
from app.forms import CoachingForm, ProjectLeaderNoteForm

# <<< GEÄNDERT >>> Importiere die ARCHIV Konstante
from app.utils import role_required, ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_TEAMLEITER, ROLE_ABTEILUNGSLEITER, ARCHIV_TEAM_NAME

from sqlalchemy import desc, func, or_, and_
from datetime import datetime, timedelta, timezone
import sqlalchemy
from calendar import monthrange

bp = Blueprint('main', __name__)

# --- HILFSFUNKTIONEN FÜR DATENAGGREGATION ---
def get_month_name_german(month_number):
    months_german = {1:"Januar",2:"Februar",3:"März",4:"April",5:"Mai",6:"Juni",7:"Juli",8:"August",9:"September",10:"Oktober",11:"November",12:"Dezember"}
    return months_german.get(month_number, "")

def calculate_date_range(period_filter_str=None):
    now = datetime.now(timezone.utc); start_date, end_date = None, None
    if not period_filter_str or period_filter_str == 'all': return None, None
    if period_filter_str == '7days': start_date=(now-timedelta(days=6)).replace(hour=0,minute=0,second=0,microsecond=0); end_date=now.replace(hour=23,minute=59,second=59,microsecond=999999)
    elif period_filter_str == '30days': start_date=(now-timedelta(days=29)).replace(hour=0,minute=0,second=0,microsecond=0); end_date=now.replace(hour=23,minute=59,second=59,microsecond=999999)
    elif period_filter_str == 'current_quarter':
        c_month=now.month; yr=now.year
        if 1<=c_month<=3: start_date,end_date=datetime(yr,1,1,0,0,0,tzinfo=timezone.utc),datetime(yr,3,monthrange(yr,3)[1],23,59,59,999999,tzinfo=timezone.utc)
        elif 4<=c_month<=6: start_date,end_date=datetime(yr,4,1,0,0,0,tzinfo=timezone.utc),datetime(yr,6,monthrange(yr,6)[1],23,59,59,999999,tzinfo=timezone.utc)
        elif 7<=c_month<=9: start_date,end_date=datetime(yr,7,1,0,0,0,tzinfo=timezone.utc),datetime(yr,9,monthrange(yr,9)[1],23,59,59,999999,tzinfo=timezone.utc)
        else: start_date,end_date=datetime(yr,10,1,0,0,0,tzinfo=timezone.utc),datetime(yr,12,monthrange(yr,12)[1],23,59,59,999999,tzinfo=timezone.utc)
    elif period_filter_str == 'current_year': yr=now.year; start_date,end_date=datetime(yr,1,1,0,0,0,tzinfo=timezone.utc),datetime(yr,12,monthrange(yr,12)[1],23,59,59,999999,tzinfo=timezone.utc)
    elif '-' in period_filter_str and len(period_filter_str)==7:
        try: 
            y_s,m_s=period_filter_str.split('-'); yr=int(y_s); m_i=int(m_s)
            if 1<=m_i<=12: 
                start_date=datetime(yr,m_i,1,0,0,0,tzinfo=timezone.utc)
                end_date=datetime(yr,m_i,monthrange(yr,m_i)[1],23,59,59,999999,tzinfo=timezone.utc)
        except ValueError: 
            pass           
    return start_date,end_date

def get_filtered_coachings_subquery(period_filter_str=None):
    q = db.session.query(Coaching.id.label("coaching_id_sq"),Coaching.team_member_id.label("team_member_id_sq"),Coaching.performance_mark.label("performance_mark_sq"),Coaching.time_spent.label("time_spent_sq"),Coaching.coaching_subject.label("coaching_subject_sq"))
    s_d,e_d = calculate_date_range(period_filter_str)
    if s_d: q=q.filter(Coaching.coaching_date>=s_d)
    if e_d: q=q.filter(Coaching.coaching_date<=e_d)
    return q.subquery('filtered_coachings_sq')

def get_performance_data_for_charts(period_filter_str=None, selected_team_id_str=None):
    sq = get_filtered_coachings_subquery(period_filter_str)
    q = db.session.query(
        Team.id.label('team_id'),
        Team.name.label('team_name'),
        func.coalesce(func.avg(sq.c.performance_mark_sq), 0).label('avg_perf_mark'),
        func.coalesce(func.sum(sq.c.time_spent_sq), 0).label('total_time'),
        func.coalesce(func.count(sq.c.coaching_id_sq), 0).label('num_coachings')
    ).select_from(Team)\
     .outerjoin(TeamMember, Team.id == TeamMember.team_id)\
     .outerjoin(sq, TeamMember.id == sq.c.team_member_id_sq)

    q = q.filter(Team.name != ARCHIV_TEAM_NAME)

    if selected_team_id_str and selected_team_id_str.isdigit():
        q = q.filter(Team.id == int(selected_team_id_str))

    res = q.group_by(Team.id, Team.name).order_by(Team.name).all()
    avg_perf_pcnt = [round(r.avg_perf_mark * 10, 2) if r.avg_perf_mark is not None else 0 for r in res]
    total_time_spent_values_list = [r.total_time for r in res]

    return {
        'labels': [r.team_name for r in res],
        'avg_performance_values': avg_perf_pcnt,
        'total_time_spent_values': total_time_spent_values_list,
        'coachings_done_values': [r.num_coachings for r in res]
    }

def get_coaching_subject_distribution(period_filter_str=None, selected_team_id_str=None):
    sq=get_filtered_coachings_subquery(period_filter_str)
    q=db.session.query(sq.c.coaching_subject_sq.label('subject'),func.count(sq.c.coaching_id_sq).label('count')).select_from(sq).filter(sq.c.coaching_subject_sq.isnot(None)).filter(sq.c.coaching_subject_sq != '')
    
    q = q.join(TeamMember, sq.c.team_member_id_sq == TeamMember.id)\
         .join(Team, TeamMember.team_id == Team.id)\
         .filter(Team.name != ARCHIV_TEAM_NAME)
         
    if selected_team_id_str and selected_team_id_str.isdigit(): 
        q = q.filter(TeamMember.team_id==int(selected_team_id_str))

    res=q.group_by(sq.c.coaching_subject_sq).order_by(desc('count')).all()
    return {'labels':[r.subject for r in res if r.subject],'values':[r.count for r in res if r.subject]}

@bp.route('/')
@bp.route('/index')
@login_required
def index():
    page=request.args.get('page',1,type=int); period_arg=request.args.get('period','all'); team_arg=request.args.get('team',"all"); search_arg=request.args.get('search',default="",type=str).strip()
    
    global_q=Coaching.query.join(TeamMember, Coaching.team_member_id == TeamMember.id)\
                          .join(Team, TeamMember.team_id == Team.id)\
                          .filter(Team.name != ARCHIV_TEAM_NAME)
                          
    gs_d,ge_d=calculate_date_range(period_arg)
    if gs_d: global_q=global_q.filter(Coaching.coaching_date>=gs_d)
    if ge_d: global_q=global_q.filter(Coaching.coaching_date<=ge_d)
    global_total_coachings=global_q.count(); global_time_obj=global_q.with_entities(func.sum(Coaching.time_spent)).scalar(); global_time=global_time_obj if global_time_obj else 0
    global_time_display=f"{global_time//60} Std. {global_time%60} Min. ({global_time} Min.)"
    
    list_q=Coaching.query.join(TeamMember,Coaching.team_member_id==TeamMember.id).join(Team, TeamMember.team_id == Team.id).join(User,Coaching.coach_id==User.id,isouter=True)
    list_q = list_q.filter(Team.name != ARCHIV_TEAM_NAME)

    ls_d,le_d=calculate_date_range(period_arg)
    if ls_d: list_q=list_q.filter(Coaching.coaching_date>=ls_d)
    if le_d: list_q=list_q.filter(Coaching.coaching_date<=le_d)
    if current_user.role==ROLE_TEAMLEITER:
        if not current_user.team_id_if_leader: flash("Kein Team zugewiesen.","warning"); list_q=list_q.filter(sqlalchemy.sql.false())
        else:
            tm_ids=[m.id for m in TeamMember.query.filter_by(team_id=current_user.team_id_if_leader).all()]
            if not tm_ids: list_q=list_q.filter(Coaching.coach_id==current_user.id) 
            else: list_q=list_q.filter(or_(Coaching.team_member_id.in_(tm_ids),Coaching.coach_id==current_user.id))
    elif team_arg and team_arg.isdigit(): list_q=list_q.filter(TeamMember.team_id==int(team_arg))
    if search_arg: list_q=list_q.filter(or_(TeamMember.name.ilike(f"%{search_arg}%"),User.username.ilike(f"%{search_arg}%"),Coaching.coaching_subject.ilike(f"%{search_arg}%")))
    total_filtered_list=list_q.count()
    coachings_page=list_q.order_by(desc(Coaching.coaching_date)).paginate(page=page,per_page=10,error_out=False)
    
    chart_perf=get_performance_data_for_charts(period_arg,team_arg) 
    chart_subj=get_coaching_subject_distribution(period_arg,team_arg)
    
    all_teams_dd=Team.query.filter(Team.name != ARCHIV_TEAM_NAME).order_by(Team.name).all()

    now=datetime.now(timezone.utc); cy=now.year; py=cy-1; m_opts=[]
    for m in range(12,0,-1): m_opts.append({'value':f"{py}-{m:02d}",'text':f"{get_month_name_german(m)} {py}"})
    for m in range(now.month,0,-1): m_opts.append({'value':f"{cy}-{m:02d}",'text':f"{get_month_name_german(m)} {cy}"})
    
    return render_template('main/index.html',
                           title='Coaching - Dashboard',
                           coachings_paginated=coachings_page,
                           total_coachings=total_filtered_list,
                           chart_labels=chart_perf['labels'],
                           chart_avg_performance_mark_percentage=chart_perf['avg_performance_values'],
                           chart_total_time_spent=chart_perf['total_time_spent_values'],
                           chart_coachings_done=chart_perf['coachings_done_values'],
                           subject_chart_labels=chart_subj['labels'],
                           subject_chart_values=chart_subj['values'],
                           all_teams_for_filter=all_teams_dd,
                           current_period_filter=period_arg,
                           current_team_id_filter=team_arg,
                           current_search_term=search_arg,
                           global_total_coachings_count=global_total_coachings,
                           global_time_coached_display=global_time_display,
                           month_options=m_opts,
                           config=current_app.config)

@bp.route('/team_view', methods=['GET'])
@login_required
@role_required([ROLE_TEAMLEITER, ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_ABTEILUNGSLEITER])
def team_view():
    selected_team_object = None; team_coachings_list_for_display = []; team_members_stats = []; view_team_id_arg = request.args.get('team_id', type=int); page_title = "Team Ansicht"

    if current_user.role == ROLE_TEAMLEITER and not view_team_id_arg:
        if not current_user.team_id_if_leader: flash("Ihnen ist kein Team zugewiesen.","warning"); return redirect(url_for('main.index'))
        selected_team_object = Team.query.get(current_user.team_id_if_leader)
        if selected_team_object: page_title = f"Mein Team: {selected_team_object.name}"
        else: flash("Zugewiesenes Team nicht gefunden.", "danger"); return redirect(url_for('main.index'))
    elif view_team_id_arg:
        if current_user.role not in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_ABTEILUNGSLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]: abort(403) 
        selected_team_object = Team.query.get(view_team_id_arg)
        if selected_team_object: 
            if selected_team_object.name == ARCHIV_TEAM_NAME:
                page_title = f"Ansicht: {selected_team_object.name}"
            else:
                page_title = f"Team Ansicht: {selected_team_object.name}"
    else: 
        if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_ABTEILUNGSLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
            selected_team_object = Team.query.filter(Team.name != ARCHIV_TEAM_NAME).order_by(Team.name).first()
            if selected_team_object: page_title = f"Team Ansicht: {selected_team_object.name}"

    if not selected_team_object:
        flash("Kein Team zum Anzeigen ausgewählt oder vorhanden.", "info")
        all_teams_for_selection = []
        if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_ABTEILUNGSLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
            all_teams_for_selection = Team.query.filter(Team.name != ARCHIV_TEAM_NAME).order_by(Team.name).all()
        return render_template('main/team_view.html', title="Team Auswählen", team=None, all_teams_list=all_teams_for_selection, team_members_performance=[], team_coachings=[], config=current_app.config)

    team_member_ids_in_selected_team = [member.id for member in selected_team_object.members]
    if team_member_ids_in_selected_team:
        team_coachings_list_for_display = Coaching.query.filter(Coaching.team_member_id.in_(team_member_ids_in_selected_team)).order_by(desc(Coaching.coaching_date)).limit(10).all()

    for member in selected_team_object.members.all(): 
        member_coachings_list = Coaching.query.filter_by(team_member_id=member.id).all()
        avg_score_val = sum(c.overall_score for c in member_coachings_list) / len(member_coachings_list) if member_coachings_list else 0.0
        leitfaden_adherences_percentages = [c.leitfaden_erfuellung_prozent for c in member_coachings_list if c.leitfaden_erfuellung_prozent is not None]
        avg_leitfaden_adherence_val = sum(leitfaden_adherences_percentages) / len(leitfaden_adherences_percentages) if leitfaden_adherences_percentages else 0.0
        total_coaching_time_minutes_val = sum(c.time_spent for c in member_coachings_list if c.time_spent is not None)
        hours = total_coaching_time_minutes_val // 60; minutes = total_coaching_time_minutes_val % 60
        formatted_time_str = f"{hours} Std. {minutes} Min."
        team_members_stats.append({'id': member.id, 'name': member.name, 'avg_score': round(avg_score_val, 2), 'avg_leitfaden_adherence': round(avg_leitfaden_adherence_val, 1), 'total_coachings': len(member_coachings_list), 'raw_total_coaching_time': total_coaching_time_minutes_val, 'formatted_total_coaching_time': formatted_time_str})
        
    all_teams_for_dropdown = []
    if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_ABTEILUNGSLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
        all_teams_for_dropdown = Team.query.filter(Team.name != ARCHIV_TEAM_NAME).order_by(Team.name).all()
        
    return render_template('main/team_view.html', 
                           title=page_title, team=selected_team_object, 
                           team_coachings=team_coachings_list_for_display, 
                           team_members_performance=team_members_stats, 
                           all_teams_list=all_teams_for_dropdown, 
                           config=current_app.config)

@bp.route('/coaching/add', methods=['GET', 'POST'])
@login_required
@role_required([ROLE_TEAMLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_ADMIN])
def add_coaching():
    user_team_id = current_user.team_id_if_leader if current_user.role == ROLE_TEAMLEITER else None
    form = CoachingForm(current_user_role=current_user.role, current_user_team_id=user_team_id)
    form.update_team_member_choices(exclude_archiv=True)
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

@bp.route('/coaching/<int:coaching_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_coaching(coaching_id):
    coaching_to_edit = Coaching.query.get_or_404(coaching_id)
    if not (current_user.id == coaching_to_edit.coach_id or current_user.role == ROLE_ADMIN):
        flash('Sie haben keine Berechtigung, dieses Coaching zu bearbeiten.', 'danger'); abort(403)
    form_user_role = current_user.role; form_user_team_id = None
    if current_user.id == coaching_to_edit.coach_id and current_user.role == ROLE_TEAMLEITER: form_user_team_id = current_user.team_id_if_leader
    elif current_user.role == ROLE_ADMIN: form_user_role = ROLE_ADMIN
    form = CoachingForm(obj=coaching_to_edit, current_user_role=form_user_role, current_user_team_id=form_user_team_id)
    form.update_team_member_choices(exclude_archiv=False)
    if form.validate_on_submit():
        try:
            form.populate_obj(coaching_to_edit)
            if coaching_to_edit.coaching_style != 'TCAP': coaching_to_edit.tcap_id = None
            db.session.commit(); flash('Coaching erfolgreich aktualisiert!', 'success')
            return redirect(request.args.get('next') or url_for('main.index'))
        except Exception as e: db.session.rollback(); current_app.logger.error(f"Update coaching ID {coaching_id} error: {e}"); flash(f'Fehler: {str(e)}', 'danger')
    if request.method == 'GET' or not form.validate_on_submit(): 
        form.team_member_id.data = coaching_to_edit.team_member_id 
    tcap_js="document.addEventListener('DOMContentLoaded',function(){var s=document.getElementById('coaching_style'),t=document.getElementById('tcap_id_field'),i=document.getElementById('tcap_id');function o(){if(s&&t&&i)if(s.value==='TCAP'){t.style.display='';i.required=!0}else{t.style.display='none';i.required=!1}}s&&t&&i&&(s.addEventListener('change',o),o())});"
    return render_template('main/add_coaching.html',title=f'Coaching ID {coaching_to_edit.id} Bearbeiten',form=form,is_edit_mode=True,coaching=coaching_to_edit, coaching_id_being_edited=coaching_to_edit.id,tcap_js=tcap_js,config=current_app.config)

@bp.route('/coaching_review_dashboard', methods=['GET', 'POST']) 
@login_required
@role_required([ROLE_PROJEKTLEITER, ROLE_QM, ROLE_ABTEILUNGSLEITER])
def pl_qm_dashboard():
    page = request.args.get('page', 1, type=int)
    selected_team_id_filter_str = request.args.get('team_id_filter', None) 

    coachings_query = Coaching.query.join(TeamMember).join(Team).filter(Team.name != ARCHIV_TEAM_NAME)
    coachings_paginated = coachings_query.order_by(desc(Coaching.coaching_date)).paginate(page=page, per_page=10, error_out=False)
    note_form = ProjectLeaderNoteForm()
    title = "Notizen Dashboard" 
    if current_user.role == ROLE_QM: title = "Quality Coach Dashboard"
    elif current_user.role == ROLE_PROJEKTLEITER: title = "Projektleiter Dashboard"
    elif current_user.role == ROLE_ABTEILUNGSLEITER: title = "Abteilungsleiter Dashboard"

    if request.method == 'POST' and 'submit_note' in request.form:
        form_val = ProjectLeaderNoteForm(request.form)
        coaching_id_str = request.form.get('coaching_id')
        if not coaching_id_str or not coaching_id_str.isdigit():
            flash("Gültige Coaching-ID fehlt.",'danger')
        elif form_val.validate():
            try:
                coaching = Coaching.query.get_or_404(int(coaching_id_str))
                coaching.project_leader_notes = form_val.notes.data
                db.session.commit()
                flash(f'Notiz für Coaching ID {coaching_id_str} gespeichert.', 'success')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Note save error: {e}")
                flash('Fehler Notizspeicherung.', 'danger')
        else:
            for f, errs in form_val.errors.items():
                flash(f"Validierungsfehler '{form_val[f].label.text}': {'; '.join(errs)}", 'danger')
        return redirect(url_for('main.pl_qm_dashboard', 
                                page=request.args.get('page',1,type=int), 
                                team_id_filter=selected_team_id_filter_str))

    all_teams_data = []
    for team_obj_stat_loop in Team.query.filter(Team.name != ARCHIV_TEAM_NAME).all():
        stats = db.session.query(
            func.coalesce(func.avg(Coaching.performance_mark * 10.0), 0).label('avg_perf'),
            func.coalesce(func.sum(Coaching.time_spent), 0).label('total_time'),
            func.coalesce(func.count(Coaching.id), 0).label('num_coachings')
        ).join(TeamMember, Coaching.team_member_id == TeamMember.id)\
         .filter(TeamMember.team_id == team_obj_stat_loop.id).first()
        all_teams_data.append({
            'id': team_obj_stat_loop.id, 'name': team_obj_stat_loop.name,
            'num_coachings': stats.num_coachings if stats else 0,
            'avg_score': round(stats.avg_perf, 2) if stats else 0,
            'total_time': stats.total_time if stats else 0
        })
    sorted_data = sorted(all_teams_data, key=lambda x: (x.get('avg_score', 0), x.get('num_coachings', 0)), reverse=True)
    top_3 = sorted_data[:3]
    teams_c = [t for t in all_teams_data if t.get('num_coachings', 0) > 0]
    flop_3 = sorted(teams_c, key=lambda x: (x.get('avg_score', 0), -x.get('num_coachings', 0)))[:3] if teams_c else []

    all_teams_for_filter_dropdown = Team.query.filter(Team.name != ARCHIV_TEAM_NAME).order_by(Team.name).all()
    selected_team_object_for_cards = None
    members_data_for_cards = []

    if selected_team_id_filter_str and selected_team_id_filter_str.isdigit():
        selected_team_id = int(selected_team_id_filter_str)
        selected_team_object_for_cards = Team.query.get(selected_team_id)
        if selected_team_object_for_cards:
            for member in selected_team_object_for_cards.members.all(): 
                member_coachings_list = Coaching.query.filter_by(team_member_id=member.id).all()
                
                # <<< KORREKTUR WAR HIER >>>
                avg_score_val = sum(c.overall_score for c in member_coachings_list) / len(member_coachings_list) if member_coachings_list else 0.0

                leitfaden_adherences_percentages = [
                    c.leitfaden_erfuellung_prozent for c in member_coachings_list if c.leitfaden_erfuellung_prozent is not None
                ]
                avg_leitfaden_adherence_val = sum(leitfaden_adherences_percentages) / len(leitfaden_adherences_percentages) if leitfaden_adherences_percentages else 0.0
                total_coaching_time_minutes_val = sum(c.time_spent for c in member_coachings_list if c.time_spent is not None)
                hours = total_coaching_time_minutes_val // 60; minutes = total_coaching_time_minutes_val % 60
                formatted_time_str = f"{hours} Std. {minutes} Min."
                members_data_for_cards.append({
                    'id': member.id, 'name': member.name, 
                    'avg_score': round(avg_score_val, 2), 
                    'avg_leitfaden_adherence': round(avg_leitfaden_adherence_val, 1),
                    'total_coachings': len(member_coachings_list), 
                    'raw_total_coaching_time': total_coaching_time_minutes_val, 
                    'formatted_total_coaching_time': formatted_time_str
                })
    return render_template('main/projektleiter_dashboard.html',
                           title=title, coachings_paginated=coachings_paginated,
                           note_form=note_form, top_3_teams=top_3, flop_3_teams=flop_3,
                           all_teams_for_filter=all_teams_for_filter_dropdown, 
                           selected_team_id_filter=selected_team_id_filter_str, 
                           selected_team_object_for_cards=selected_team_object_for_cards, 
                           members_data_for_cards=members_data_for_cards, 
                           config=current_app.config)

@bp.route('/api/member_coaching_trend', methods=['GET'])
@login_required 
def get_member_coaching_trend():
    team_member_id_str = request.args.get('team_member_id')
    count_str = request.args.get('count', '10') 
    if not team_member_id_str: return jsonify({"error": "Team Member ID (team_member_id) is required"}), 400
    try: team_member_id = int(team_member_id_str)
    except ValueError: return jsonify({"error": "Invalid Team Member ID format"}), 400
    query = Coaching.query.filter_by(team_member_id=team_member_id).order_by(Coaching.coaching_date.desc()) 
    if count_str.lower() != 'all':
        try:
            count = int(count_str)
            if count <= 0: return jsonify({"error": "Count must be a positive integer or 'all'"}), 400
            query = query.limit(count)
        except ValueError: return jsonify({"error": "Invalid count format"}), 400
    recent_coachings = query.all(); recent_coachings.reverse() 
    if not recent_coachings: return jsonify({"labels": [], "scores": [], "dates": []})
    labels = []; scores = []; dates = []  
    for i, coaching in enumerate(recent_coachings):
        labels.append(f"Coaching {i+1}") 
        scores.append(coaching.overall_score if coaching.overall_score is not None else 0)
        dates.append(coaching.coaching_date.strftime('%d.%m.%y'))
    return jsonify({"labels": labels, "scores": scores, "dates": dates})
