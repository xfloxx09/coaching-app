# app/main_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import User, Team, TeamMember, Coaching 
from app.forms import CoachingForm, ProjectLeaderNoteForm # Annahme: Diese sind korrekt
from app.utils import role_required, ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_TEAMLEITER
from sqlalchemy import desc, func, or_, and_ # and_ hinzugefügt für komplexe Filter
from datetime import datetime, timedelta, timezone
import sqlalchemy # Für sqlalchemy.sql.false()

bp = Blueprint('main', __name__)

# --- HILFSFUNKTIONEN FÜR DATENAGGREGATION ---

def get_filtered_coachings_subquery(date_from_str=None, date_to_str=None):
    """ Erstellt eine Subquery für Coachings, optional gefiltert nach Datumsbereich. """
    coachings_base_q = db.session.query(
        Coaching.id.label("coaching_id_sq"),
        Coaching.team_member_id.label("team_member_id_sq"),
        Coaching.performance_mark.label("performance_mark_sq"),
        Coaching.time_spent.label("time_spent_sq"),
        Coaching.coaching_subject.label("coaching_subject_sq"),
        Coaching.coaching_date # Wird für den Datumsfilter in der Subquery benötigt
    )
    if date_from_str:
        try:
            date_from_obj = datetime.strptime(date_from_str, '%Y-%m-%d').replace(hour=0, minute=0, second=0, tzinfo=timezone.utc)
            coachings_base_q = coachings_base_q.filter(Coaching.coaching_date >= date_from_obj)
        except ValueError:
            flash(f"Ungültiges 'Von Datum' Format: {date_from_str}. Bitte YYYY-MM-DD verwenden.", "warning")
            pass 

    if date_to_str:
        try:
            date_to_obj = datetime.strptime(date_to_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
            coachings_base_q = coachings_base_q.filter(Coaching.coaching_date <= date_to_obj)
        except ValueError:
            flash(f"Ungültiges 'Bis Datum' Format: {date_to_str}. Bitte YYYY-MM-DD verwenden.", "warning")
            pass
            
    return coachings_base_q.subquery('filtered_coachings_sq')


def get_performance_data_for_charts(date_from_str=None, date_to_str=None, selected_team_id_str=None):
    """ Aggregiert Coaching-Daten für die Performance-Charts. """
    
    filtered_coachings_sq = get_filtered_coachings_subquery(date_from_str, date_to_str)

    query = db.session.query(
        Team.id.label('team_id'),
        Team.name.label('team_name'),
        func.coalesce(func.avg(filtered_coachings_sq.c.performance_mark_sq * 10.0), 0).label('avg_performance_mark_scaled'),
        func.coalesce(func.sum(filtered_coachings_sq.c.time_spent_sq), 0).label('total_time_spent'),
        func.coalesce(func.count(filtered_coachings_sq.c.coaching_id_sq), 0).label('coachings_done')
    ).select_from(Team)\
     .outerjoin(TeamMember, Team.id == TeamMember.team_id)\
     .outerjoin(filtered_coachings_sq, TeamMember.id == filtered_coachings_sq.c.team_member_id_sq)

    if selected_team_id_str and selected_team_id_str.isdigit():
        query = query.filter(Team.id == int(selected_team_id_str))

    results = query.group_by(Team.id, Team.name).order_by(Team.name).all()
    
    chart_data = {
        'labels': [r.team_name for r in results],
        'avg_performance_values': [round(r.avg_performance_mark_scaled, 2) for r in results],
        'avg_time_spent_values': [round(r.total_time_spent / r.coachings_done, 2) if r.coachings_done > 0 else 0 for r in results],
        'coachings_done_values': [r.coachings_done for r in results]
    }
    return chart_data

def get_coaching_subject_distribution(date_from_str=None, date_to_str=None, selected_team_id_str=None):
    """ Ermittelt die Verteilung der Coaching-Themen. """
    
    filtered_coachings_sq = get_filtered_coachings_subquery(date_from_str, date_to_str)

    query = db.session.query(
        filtered_coachings_sq.c.coaching_subject_sq.label('coaching_subject'), 
        func.count(filtered_coachings_sq.c.coaching_id_sq).label('count')
    ).select_from(filtered_coachings_sq)\
     .filter(filtered_coachings_sq.c.coaching_subject_sq.isnot(None)) # Nur Coachings mit gesetztem Thema

    if selected_team_id_str and selected_team_id_str.isdigit():
        # Um nach Team zu filtern, müssen wir TeamMember mit der Subquery verbinden
        # (angenommen, TeamMember.id ist in der Subquery als team_member_id_sq vorhanden)
        query = query.join(TeamMember, filtered_coachings_sq.c.team_member_id_sq == TeamMember.id)\
                     .filter(TeamMember.team_id == int(selected_team_id_str))
    
    results = query.group_by(filtered_coachings_sq.c.coaching_subject_sq).order_by(desc('count')).all()

    subject_data = {
        'labels': [r.coaching_subject for r in results if r.coaching_subject],
        'values': [r.count for r in results if r.coaching_subject]
    }
    return subject_data


@bp.route('/')
@bp.route('/index')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    date_from_arg = request.args.get('date_from') 
    date_to_arg = request.args.get('date_to')     
    team_filter_arg = request.args.get('team', "all") 

    # --- Daten für die paginierte Coaching-Liste ---
    coachings_list_query = Coaching.query 

    # Datumsfilter für die Liste
    if date_from_arg:
        try:
            date_from_obj = datetime.strptime(date_from_arg, '%Y-%m-%d').replace(hour=0, minute=0, second=0, tzinfo=timezone.utc)
            coachings_list_query = coachings_list_query.filter(Coaching.coaching_date >= date_from_obj)
        except ValueError: pass
    if date_to_arg:
        try:
            date_to_obj = datetime.strptime(date_to_arg, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
            coachings_list_query = coachings_list_query.filter(Coaching.coaching_date <= date_to_obj)
        except ValueError: pass

    # Rollen- und Teamfilter für die Liste
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
    elif team_filter_arg and team_filter_arg.isdigit(): # Für Admins etc., wenn ein spezifisches Team ausgewählt ist
            team_id_int = int(team_filter_arg)
            coachings_list_query = coachings_list_query.join(TeamMember).filter(TeamMember.team_id == team_id_int)
    # Wenn Admin etc. und "Alle Teams" (team_filter_arg == "all"), wird die Liste nicht weiter nach Team gefiltert

    coachings_paginated = coachings_list_query.order_by(desc(Coaching.coaching_date)).paginate(page=page, per_page=10, error_out=False)
    total_coachings_in_list = coachings_list_query.count() # count() auf die möglicherweise gefilterte Query
    
    # --- Daten für die Charts ---
    # Die Filterargumente date_from_arg, date_to_arg, team_filter_arg werden direkt an die Chart-Funktionen übergeben
    chart_data = get_performance_data_for_charts(date_from_arg, date_to_arg, team_filter_arg)
    subject_distribution_data = get_coaching_subject_distribution(date_from_arg, date_to_arg, team_filter_arg)
    
    all_teams_for_filter_dropdown = Team.query.order_by(Team.name).all()
    
    # Debug-Prints hier, wie du sie hattest, sind gut zum Überprüfen.
    # print("---- DEBUG: Daten für index.html Template ----")
    # ...

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
                           current_date_from=date_from_arg, # Für Vorbelegung der Filterfelder
                           current_date_to=date_to_arg,     # Für Vorbelegung
                           current_team_id_filter=team_filter_arg)

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
        if team: page_title_prefix = "Mein Team" # Titelanpassung
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
        team_coachings_query = Coaching.query.filter(Coaching.team_member_id.in_(team_member_ids))
        team_coachings_list = team_coachings_query.order_by(desc(Coaching.coaching_date)).limit(20).all()
        for member in team.members:
            member_coachings = member.coachings_received.all() 
            avg_score = sum(c.overall_score for c in member_coachings) / len(member_coachings) if member_coachings else 0
            total_time = sum(c.time_spent for c in member_coachings if c.time_spent is not None) # Sicherstellen, dass time_spent nicht None ist
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
                    document.getElementById('tcap_id').required = true;
                } else {
                    tcapIdField.style.display = 'none';
                    document.getElementById('tcap_id').value = '';
                    document.getElementById('tcap_id').required = false;
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
    coachings_query = Coaching.query.order_by(desc(Coaching.coaching_date))
    coachings_paginated = coachings_query.paginate(page=page, per_page=10, error_out=False)
    note_form_display = ProjectLeaderNoteForm() 
    dashboard_title = "Review Dashboard"
    if current_user.role == ROLE_PROJEKTLEITER: dashboard_title = "Projektleiter Dashboard"
    elif current_user.role == ROLE_QM: dashboard_title = "Quality Coach Dashboard"

    if request.method == 'POST' and 'submit_note' in request.form:
        form_to_validate = ProjectLeaderNoteForm(request.form) 
        coaching_id_str = request.form.get('coaching_id')
        form_errors = False
        if not coaching_id_str:
            flash("Coaching-ID fehlt oder konnte nicht übermittelt werden.", 'danger')
            form_errors = True
        if not form_to_validate.validate(): # Validiert 'notes' und CSRF
            for fieldName, errorMessages in form_to_validate.errors.items():
                for err in errorMessages: 
                    flash(f"Validierungsfehler im Feld '{form_to_validate[fieldName].label.text}': {err}", 'danger')
            form_errors = True
        if not form_errors:
            notes_data = form_to_validate.notes.data
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
         .filter(TeamMember.team_id == team_obj.id).first()
        if team_stats: # team_stats kann None sein, wenn ein Team keine Coachings hat
            all_teams_data.append({
                'id': team_obj.id, 'name': team_obj.name,
                'num_coachings': team_stats.num_coachings if team_stats.num_coachings is not None else 0,
                'avg_score': round(team_stats.avg_performance_mark_scaled, 2) if team_stats.avg_performance_mark_scaled is not None else 0, 
                'total_time': team_stats.total_time if team_stats.total_time is not None else 0
            })
        else: # Fallback, falls team_stats None ist
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
