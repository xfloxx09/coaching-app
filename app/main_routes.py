# app/main_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import User, Team, TeamMember, Coaching 
from app.forms import CoachingForm, ProjectLeaderNoteForm 
from app.utils import role_required, ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_TEAMLEITER
from sqlalchemy import desc, func, or_, and_
from datetime import datetime, timedelta, timezone
import sqlalchemy 
from calendar import monthrange # Für die Berechnung des letzten Tages im Monat

bp = Blueprint('main', __name__)

# --- HILFSFUNKTIONEN FÜR DATENAGGREGATION ---

def calculate_date_range(period_filter_str=None):
    """
    Berechnet start_date und end_date basierend auf dem period_filter_str.
    Gibt (start_date, end_date) oder (None, None) zurück.
    """
    now = datetime.now(timezone.utc)
    start_date, end_date = None, None 

    if not period_filter_str or period_filter_str == 'all':
        return None, None

    if period_filter_str == '7days':
        start_date = now - timedelta(days=6) 
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period_filter_str == '30days':
        start_date = now - timedelta(days=29)
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period_filter_str == 'current_quarter':
        current_month = now.month
        year = now.year
        if 1 <= current_month <= 3: 
            start_date = datetime(year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            end_date = datetime(year, 3, monthrange(year, 3)[1], 23, 59, 59, 999999, tzinfo=timezone.utc)
        elif 4 <= current_month <= 6: 
            start_date = datetime(year, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
            end_date = datetime(year, 6, monthrange(year, 6)[1], 23, 59, 59, 999999, tzinfo=timezone.utc)
        elif 7 <= current_month <= 9: 
            start_date = datetime(year, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
            end_date = datetime(year, 9, monthrange(year, 9)[1], 23, 59, 59, 999999, tzinfo=timezone.utc)
        else: 
            start_date = datetime(year, 10, 1, 0, 0, 0, tzinfo=timezone.utc)
            end_date = datetime(year, 12, monthrange(year, 12)[1], 23, 59, 59, 999999, tzinfo=timezone.utc)
    elif period_filter_str == 'current_year':
        year = now.year
        start_date = datetime(year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_date = datetime(year, 12, monthrange(year, 12)[1], 23, 59, 59, 999999, tzinfo=timezone.utc)
    
    return start_date, end_date

def get_filtered_coachings_subquery(period_filter_str=None):
    """ Erstellt eine Subquery für Coachings, optional gefiltert nach Datum. """
    coachings_base_q = db.session.query(
        Coaching.id.label("coaching_id_sq"),
        Coaching.team_member_id.label("team_member_id_sq"),
        Coaching.performance_mark.label("performance_mark_sq"),
        Coaching.time_spent.label("time_spent_sq"),
        Coaching.coaching_subject.label("coaching_subject_sq")
    ).filter(Coaching.is_archived == False) # Annahme: is_archived existiert und soll gefiltert werden
                                        # Wenn nicht, diese Zeile entfernen oder anpassen.
    
    start_date, end_date = calculate_date_range(period_filter_str)
    if start_date:
        coachings_base_q = coachings_base_q.filter(Coaching.coaching_date >= start_date)
    if end_date:
        coachings_base_q = coachings_base_q.filter(Coaching.coaching_date <= end_date)
    return coachings_base_q.subquery('filtered_coachings_sq')

def get_performance_data_for_charts(period_filter_str=None, selected_team_id_str=None):
    filtered_coachings_sq = get_filtered_coachings_subquery(period_filter_str)
    query = db.session.query(
        Team.id.label('team_id'), Team.name.label('team_name'),
        func.coalesce(func.avg(filtered_coachings_sq.c.performance_mark_sq * 10.0), 0).label('avg_performance_mark_scaled'),
        func.coalesce(func.sum(filtered_coachings_sq.c.time_spent_sq), 0).label('total_time_spent'),
        func.coalesce(func.count(filtered_coachings_sq.c.coaching_id_sq), 0).label('coachings_done')
    ).select_from(Team)\
     .outerjoin(TeamMember, Team.id == TeamMember.team_id)\
     .outerjoin(filtered_coachings_sq, TeamMember.id == filtered_coachings_sq.c.team_member_id_sq)

    if selected_team_id_str and selected_team_id_str.isdigit():
        query = query.filter(Team.id == int(selected_team_id_str))
    results = query.group_by(Team.id, Team.name).order_by(Team.name).all()
    return {
        'labels': [r.team_name for r in results],
        'avg_performance_values': [round(r.avg_performance_mark_scaled, 2) for r in results],
        'avg_time_spent_values': [round(r.total_time_spent / r.coachings_done, 2) if r.coachings_done > 0 else 0 for r in results],
        'coachings_done_values': [r.coachings_done for r in results]
    }

def get_coaching_subject_distribution(period_filter_str=None, selected_team_id_str=None):
    filtered_coachings_sq = get_filtered_coachings_subquery(period_filter_str)
    query = db.session.query(
        filtered_coachings_sq.c.coaching_subject_sq.label('coaching_subject'), 
        func.count(filtered_coachings_sq.c.coaching_id_sq).label('count')
    ).select_from(filtered_coachings_sq)\
     .filter(filtered_coachings_sq.c.coaching_subject_sq.isnot(None))

    if selected_team_id_str and selected_team_id_str.isdigit():
        query = query.join(TeamMember, filtered_coachings_sq.c.team_member_id_sq == TeamMember.id)\
                     .filter(TeamMember.team_id == int(selected_team_id_str))
    results = query.group_by(filtered_coachings_sq.c.coaching_subject_sq).order_by(desc('count')).all()
    return {
        'labels': [r.coaching_subject for r in results if r.coaching_subject],
        'values': [r.count for r in results if r.coaching_subject]
    }

@bp.route('/')
@bp.route('/index')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    period_filter_arg = request.args.get('period', 'all') 
    team_filter_arg = request.args.get('team', "all") 

    # Basis-Query für die Liste und für die Summary-Boxen
    start_date, end_date = calculate_date_range(period_filter_arg)
    if start_date:
        base_filtered_coachings_q = base_filtered_coachings_q.filter(Coaching.coaching_date >= start_date)
    if end_date:
        base_filtered_coachings_q = base_filtered_coachings_q.filter(Coaching.coaching_date <= end_date)

    # Query für die Coaching-Liste (kann weiter nach Rolle/Team gefiltert werden)
    coachings_list_query = base_filtered_coachings_q

    if current_user.role == ROLE_TEAMLEITER:
        if not current_user.team_id_if_leader:
            flash("Ihnen ist kein Team zugewiesen. Die Coaching-Liste ist leer.", "warning")
            coachings_list_query = Coaching.query.filter(sqlalchemy.sql.false()) 
        else:
            team_members_ids = [member.id for member in TeamMember.query.filter_by(team_id=current_user.team_id_if_leader).all()]
            if not team_members_ids:
                 coachings_list_query = coachings_list_query.filter(Coaching.coach_id == current_user.id)
            else: 
                coachings_list_query = coachings_list_query.filter(
                    or_(Coaching.team_member_id.in_(team_members_ids), Coaching.coach_id == current_user.id)
                )
    elif team_filter_arg and team_filter_arg.isdigit(): 
            team_id_int = int(team_filter_arg)
            coachings_list_query = coachings_list_query.join(TeamMember).filter(TeamMember.team_id == team_id_int)
    
    coachings_paginated = coachings_list_query.order_by(desc(Coaching.coaching_date)).paginate(page=page, per_page=10, error_out=False)
    total_coachings_in_list = coachings_list_query.count()
    
    # Daten für die Info-Boxen (basierend auf den globalen Filtern, ggf. mit Teamfilter)
    summary_query_for_boxes = base_filtered_coachings_q # Start mit Datums-gefilterten Coachings
    if team_filter_arg and team_filter_arg.isdigit():
        summary_query_for_boxes = summary_query_for_boxes.join(TeamMember).filter(TeamMember.team_id == int(team_filter_arg))
    
    total_filtered_coachings_count = summary_query_for_boxes.count()
    total_filtered_time_minutes_obj = summary_query_for_boxes.with_entities(func.sum(Coaching.time_spent)).scalar()
    total_filtered_time_minutes = total_filtered_time_minutes_obj if total_filtered_time_minutes_obj is not None else 0

    hours_coached = total_filtered_time_minutes // 60
    minutes_coached_remainder = total_filtered_time_minutes % 60
    time_coached_display = f"{hours_coached} Std. {minutes_coached_remainder} Min. ({total_filtered_time_minutes} Min.)"
        
    # Daten für die Charts
    chart_data = get_performance_data_for_charts(period_filter_arg, team_filter_arg)
    subject_distribution_data = get_coaching_subject_distribution(period_filter_arg, team_filter_arg)
    all_teams_for_filter_dropdown = Team.query.order_by(Team.name).all()
    
    return render_template('main/index.html', 
                           title='Dashboard - Alle Coachings',
                           coachings_paginated=coachings_paginated, 
                           total_coachings=total_coachings_in_list,
                           chart_labels=chart_data['labels'],
                           chart_avg_performance_mark_percentage=chart_data['avg_performance_values'], 
                           chart_avg_time_spent=chart_data['avg_time_spent_values'],
                           chart_coachings_done=chart_data['coachings_done_values'],
                           subject_chart_labels=subject_distribution_data['labels'],
                           subject_chart_values=subject_distribution_data['values'],
                           all_teams_for_filter=all_teams_for_filter_dropdown,
                           current_period_filter=period_filter_arg, 
                           current_team_id_filter=team_filter_arg,
                           total_filtered_coachings_count=total_filtered_coachings_count,
                           time_coached_display=time_coached_display
                           )

# --- `team_view`-Route ---
@bp.route('/team_view')
@login_required
@role_required([ROLE_TEAMLEITER, ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER])
def team_view():
    team = None
    team_coachings_list = [] 
    team_members_performance = []
    view_team_id = request.args.get('team_id', type=int)
    page_title_prefix = "Team Ansicht"

    if current_user.role == ROLE_TEAMLEITER and not view_team_id:
        if not current_user.team_id_if_leader:
            flash("Ihnen ist kein Team zugewiesen.", "warning")
            return redirect(url_for('main.index'))
        team = Team.query.get(current_user.team_id_if_leader)
        if team: page_title_prefix = "Mein Team"
    elif view_team_id:
        if current_user.role not in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
            abort(403)
        team = Team.query.get(view_team_id)
    else: 
        if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
            team = Team.query.first()
        else:
            abort(403)
            
    if not team:
        flash("Team nicht gefunden oder keine Teams im System vorhanden.", "info")
        all_teams_list = []
        if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
            all_teams_list = Team.query.order_by(Team.name).all()
        return render_template('main/team_view.html', title='Team Ansicht', team=None, all_teams_list=all_teams_list)
            
    if team:
        team_member_ids = [member.id for member in team.members]
        team_coachings_query = Coaching.query.filter(Coaching.is_archived == False, Coaching.team_member_id.in_(team_member_ids))
        team_coachings_list = team_coachings_query.order_by(desc(Coaching.coaching_date)).limit(20).all()
        for member in team.members:
            member_coachings = Coaching.query.filter_by(team_member_id=member.id, is_archived=False).all() 
            avg_score = sum(c.overall_score for c in member_coachings) / len(member_coachings) if member_coachings else 0
            total_time = sum(c.time_spent for c in member_coachings if c.time_spent is not None)
            team_members_performance.append({
                'name': member.name, 'avg_score': round(avg_score, 2),
                'total_coachings': len(member_coachings), 'total_coaching_time': total_time
            })
    all_teams_list = []
    if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
        all_teams_list = Team.query.order_by(Team.name).all()
    
    final_title = f"{page_title_prefix}: {team.name}" if team else page_title_prefix

    return render_template('main/team_view.html', 
                           title=final_title,
                           team=team, team_coachings=team_coachings_list, 
                           team_members_performance=team_members_performance,
                           all_teams_list=all_teams_list)


# --- `add_coaching`-Route ---
@bp.route('/coaching/add', methods=['GET', 'POST'])
@login_required
@role_required([ROLE_TEAMLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_ADMIN])
def add_coaching():
    user_team_id_for_form = None
    if current_user.role == ROLE_TEAMLEITER:
        user_team_id_for_form = current_user.team_id_if_leader
    form = CoachingForm(current_user_role=current_user.role, current_user_team_id=user_team_id_for_form)
    if form.validate_on_submit():
        try:
            coaching = Coaching(
                team_member_id=form.team_member_id.data, coach_id=current_user.id,
                coaching_style=form.coaching_style.data,
                tcap_id=form.tcap_id.data if form.coaching_style.data == 'TCAP' and form.tcap_id.data else None,
                coaching_subject=form.coaching_subject.data, 
                coach_notes=form.coach_notes.data if form.coach_notes.data else None,
                leitfaden_begruessung=form.leitfaden_begruessung.data,
                leitfaden_legitimation=form.leitfaden_legitimation.data,
                leitfaden_pka=form.leitfaden_pka.data, leitfaden_kek=form.leitfaden_kek.data,
                leitfaden_angebot=form.leitfaden_angebot.data,
                leitfaden_zusammenfassung=form.leitfaden_zusammenfassung.data,
                leitfaden_kzb=form.leitfaden_kzb.data, 
                performance_mark=form.performance_mark.data,
                time_spent=form.time_spent.data
                # is_archived wird standardmäßig auf False gesetzt (Modell-Default)
            )
            db.session.add(coaching)
            db.session.commit()
            flash('Coaching erfolgreich gespeichert!', 'success')
            return redirect(url_for('main.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Speichern des Coachings: {str(e)}', 'danger')
            import traceback
            traceback.print_exc()
    elif request.method == 'POST': 
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Fehler im Feld '{form[field].label.text}': {error}", 'danger')
    tcap_js = """
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
                        document.getElementById('tcap_id').value = '';
                        document.getElementById('tcap_id').required = false;
                    }
                }
            }
        }
        if(styleSelect && tcapIdField) {
            styleSelect.addEventListener('change', toggleTcapField);
            toggleTcapField(); 
        }
    });
    """
    return render_template('main/add_coaching.html', title='Coaching hinzufügen', form=form, tcap_js=tcap_js)

# --- `pl_qm_dashboard`-Route ---
@bp.route('/coaching_review_dashboard', methods=['GET', 'POST'])
@login_required
@role_required([ROLE_PROJEKTLEITER, ROLE_QM])
def pl_qm_dashboard():
    page = request.args.get('page', 1, type=int)
    coachings_query = Coaching.query.filter(Coaching.is_archived == False).order_by(desc(Coaching.coaching_date))
    coachings_paginated = coachings_query.paginate(page=page, per_page=10, error_out=False)
    note_form_display = ProjectLeaderNoteForm() 
    dashboard_title = "Review Dashboard"
    if current_user.role == ROLE_PROJEKTLEITER: dashboard_title = "Projektleiter Dashboard"
    elif current_user.role == ROLE_QM: dashboard_title = "Quality Coach Dashboard"

    if request.method == 'POST' and 'submit_note' in request.form:
        form_for_validation = ProjectLeaderNoteForm(request.form) 
        coaching_id_str = request.form.get('coaching_id')
        form_errors = False
        if not coaching_id_str:
            flash("Coaching-ID fehlt oder konnte nicht übermittelt werden.", 'danger')
            form_errors = True
        if not form_for_validation.validate():
            for fieldName, errorMessages in form_for_validation.errors.items():
                for err in errorMessages: flash(f"Validierungsfehler im Feld '{form_for_validation[fieldName].label.text}': {err}", 'danger')
            form_errors = True
        if not form_errors:
            notes_data = form_for_validation.notes.data
            try:
                coaching_id_int = int(coaching_id_str)
                coaching_to_update = Coaching.query.get_or_404(coaching_id_int)
                coaching_to_update.project_leader_notes = notes_data
                db.session.commit()
                flash(f'Notiz für Coaching ID {coaching_id_int} erfolgreich gespeichert.', 'success')
            except ValueError: flash('Ungültige Coaching-ID erhalten.', 'danger')
            except Exception as e:
                db.session.rollback()
                flash(f'Fehler beim Speichern der Notiz: {str(e)}', 'danger')
            return redirect(url_for('main.pl_qm_dashboard', page=request.args.get('page', 1, type=int)))
        else:
            return redirect(url_for('main.pl_qm_dashboard', page=page))

    all_teams_data = []
    teams_list = Team.query.all()
    for team_obj in teams_list: 
        team_stats = db.session.query(
            func.coalesce(func.avg(Coaching.performance_mark * 10.0), 0).label('avg_performance_mark_scaled'), 
            func.coalesce(func.sum(Coaching.time_spent), 0).label('total_time'),
            func.coalesce(func.count(Coaching.id), 0).label('num_coachings')
        ).join(TeamMember, Coaching.team_member_id == TeamMember.id)\
         .filter(TeamMember.team_id == team_obj.id)\
         .filter(Coaching.is_archived == False).first() # Filter für nicht-archivierte Coachings
        
        if team_stats:
            all_teams_data.append({
                'id': team_obj.id, 'name': team_obj.name,
                'num_coachings': team_stats.num_coachings if team_stats.num_coachings is not None else 0,
                'avg_score': round(team_stats.avg_performance_mark_scaled, 2) if team_stats.avg_performance_mark_scaled is not None else 0, 
                'total_time': team_stats.total_time if team_stats.total_time is not None else 0
            })
        else:
            all_teams_data.append({
                'id': team_obj.id, 'name': team_obj.name,
                'num_coachings': 0, 'avg_score': 0, 'total_time': 0
            })
            
    sorted_teams = sorted(all_teams_data, key=lambda x: (x['avg_score'], x['num_coachings']), reverse=True)
    top_3_teams = sorted_teams[:3]
    teams_with_coachings_for_flop = [t for t in all_teams_data if t['num_coachings'] > 0]
    if teams_with_coachings_for_flop:
        sorted_teams_flop = sorted(teams_with_coachings_for_flop, key=lambda x: (x['avg_score'], -x['num_coachings']))
        flop_3_teams = sorted_teams_flop[:3]
    else:
        flop_3_teams = []
        
    return render_template(
        'main/projektleiter_dashboard.html', title=dashboard_title,
        coachings_paginated=coachings_paginated, note_form=note_form_display,
        top_3_teams=top_3_teams, flop_3_teams=flop_3_teams
    )
