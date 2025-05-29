# app/main_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import User, Team, TeamMember, Coaching 
from app.forms import CoachingForm, ProjectLeaderNoteForm 
from app.utils import role_required, ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_TEAMLEITER
from sqlalchemy import desc, func, or_ # or_ hinzugefügt
from datetime import datetime, timedelta, timezone # timezone hinzugefügt
import sqlalchemy

bp = Blueprint('main', __name__)

# --- HILFSFUNKTIONEN FÜR DATENAGGREGATION ---
def get_performance_data_for_charts(days_filter_str=None, selected_team_id_str=None):
    query_elements = [
        Team.id.label('team_id'),
        Team.name.label('team_name'),
        # HIER DIE ÄNDERUNG: Wir aggregieren performance_mark direkt
        # und nennen es avg_performance_mark_percentage, um klarzustellen, dass es nicht der volle overall_score ist.
        # Da performance_mark 0-10 ist, multiplizieren wir mit 10, um es auf eine Skala von 0-100 zu bringen.
        func.coalesce(func.avg(Coaching.performance_mark * 10.0), 0).label('avg_performance_mark_percentage'), # 10.0 für Fließkomma-Division
        func.coalesce(func.sum(Coaching.time_spent), 0).label('total_time_spent'),
        func.coalesce(func.count(Coaching.id), 0).label('coachings_done')
    ]
    
    # Temporäre Tabelle/CTE für gefilterte Coachings, falls ein Datumsfilter aktiv ist
    if days_filter_str and days_filter_str.isdigit():
        days = int(days_filter_str)
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        filtered_coachings_subquery = db.session.query(
            Coaching.id.label("coaching_id"),
            Coaching.team_member_id,
            Coaching.performance_mark, # Nur die Spalte, die wir direkt aggregieren
            Coaching.time_spent
        ).filter(Coaching.coaching_date >= start_date).subquery()

        query = db.session.query(
            Team.id.label('team_id'),
            Team.name.label('team_name'),
            func.coalesce(func.avg(filtered_coachings_subquery.c.performance_mark * 10.0), 0).label('avg_performance_mark_percentage'),
            func.coalesce(func.sum(filtered_coachings_subquery.c.time_spent), 0).label('total_time_spent'),
            func.coalesce(func.count(filtered_coachings_subquery.c.coaching_id), 0).label('coachings_done')
        ).select_from(Team)\
        .outerjoin(TeamMember, Team.id == TeamMember.team_id)\
        .outerjoin(filtered_coachings_subquery, TeamMember.id == filtered_coachings_subquery.c.team_member_id)
    else:
        # Query ohne Datumsfilter
        query = db.session.query(*query_elements)\
        .select_from(Team)\
        .outerjoin(TeamMember, Team.id == TeamMember.team_id)\
        .outerjoin(Coaching, TeamMember.id == Coaching.team_member_id)

    if selected_team_id_str and selected_team_id_str.isdigit():
        query = query.filter(Team.id == int(selected_team_id_str))

    results = query.group_by(Team.id, Team.name).order_by(Team.name).all()

    chart_data = {
        'labels': [r.team_name for r in results],
        'avg_performance_values': [round(r.avg_performance_mark_percentage, 2) for r in results], # Umbenannt
        'avg_time_spent_values': [round(r.total_time_spent / r.coachings_done, 2) if r.coachings_done > 0 else 0 for r in results],
        'coachings_done_values': [r.coachings_done for r in results]
    }
    return chart_data

# Die index-Route muss dann die umbenannte Variable an das Template übergeben:
@bp.route('/')
@bp.route('/index')
@login_required
def index():
    # ... (Code für Paginierung und Filter-Argumente bleibt gleich) ...
    page = request.args.get('page', 1, type=int)
    days_filter_arg = request.args.get('days', None) 
    team_filter_arg = request.args.get('team', "all")

    # ... (Code für coachings_list_query bleibt gleich) ...
    if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
        coachings_list_query = Coaching.query
    elif current_user.role == ROLE_TEAMLEITER:
        if not current_user.team_id_if_leader:
            flash("Ihnen ist kein Team zugewiesen. Bitte kontaktieren Sie einen Admin.", "warning")
            coachings_list_query = Coaching.query.filter(sqlalchemy.sql.false()) 
        else:
            team_members_ids = [member.id for member in TeamMember.query.filter_by(team_id=current_user.team_id_if_leader).all()]
            if not team_members_ids:
                 coachings_list_query = Coaching.query.filter(Coaching.coach_id == current_user.id)
            else:
                coachings_list_query = Coaching.query.filter(
                    or_(Coaching.team_member_id.in_(team_members_ids), Coaching.coach_id == current_user.id)
                )
    else:
        coachings_list_query = Coaching.query.filter(sqlalchemy.sql.false())

    coachings_paginated = coachings_list_query.order_by(desc(Coaching.coaching_date)).paginate(page=page, per_page=10, error_out=False)
    total_coachings_in_list = coachings_list_query.count()
    
    chart_team_filter_for_func = team_filter_arg
    if current_user.role == ROLE_TEAMLEITER: 
        chart_team_filter_for_func = str(current_user.team_id_if_leader) if current_user.team_id_if_leader else "none" 

    chart_data = get_performance_data_for_charts(days_filter_arg, chart_team_filter_for_func)
    all_teams_for_filter_dropdown = Team.query.order_by(Team.name).all()

    return render_template('main/index.html', 
                           title='Dashboard - Alle Coachings',
                           coachings_paginated=coachings_paginated, 
                           total_coachings=total_coachings_in_list,
                           chart_labels=chart_data['labels'],
                           # HIER DIE UMBENENNUNG BEACHTEN:
                           chart_avg_performance_mark_percentage=chart_data['avg_performance_values'], 
                           chart_avg_time_spent=chart_data['avg_time_spent_values'],
                           chart_coachings_done=chart_data['coachings_done_values'],
                           all_teams_for_filter=all_teams_for_filter_dropdown,
                           current_days_filter=days_filter_arg,
                           current_team_id_filter=team_filter_arg)


@bp.route('/team_view')
@login_required
@role_required([ROLE_TEAMLEITER, ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER])
def team_view():
    team = None
    team_coachings_list = [] 
    team_members_performance = []
    view_team_id = request.args.get('team_id', type=int)

    if current_user.role == ROLE_TEAMLEITER and not view_team_id:
        if not current_user.team_id_if_leader:
            flash("Ihnen ist kein Team zugewiesen.", "warning")
            return redirect(url_for('main.index'))
        team = Team.query.get(current_user.team_id_if_leader)
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
            total_time = sum(c.time_spent for c in member_coachings if c.time_spent)
            team_members_performance.append({
                'name': member.name, 'avg_score': round(avg_score, 2),
                'total_coachings': len(member_coachings), 'total_coaching_time': total_time
            })
    all_teams_list = []
    if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
        all_teams_list = Team.query.order_by(Team.name).all()
    return render_template('main/team_view.html', 
                           title=f'Team Ansicht: {team.name if team else "Kein Team ausgewählt"}',
                           team=team, team_coachings=team_coachings_list, 
                           team_members_performance=team_members_performance,
                           all_teams_list=all_teams_list)

@bp.route('/coaching/add', methods=['GET', 'POST'])
@login_required
@role_required([ROLE_TEAMLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_ADMIN])
def add_coaching():
    form = CoachingForm(current_user_role=current_user.role, current_user_team_id=current_user.team_id_if_leader)
    if form.validate_on_submit():
        coaching = Coaching(
            team_member_id=form.team_member_id.data, coach_id=current_user.id,
            coaching_style=form.coaching_style.data,
            tcap_id=form.tcap_id.data if form.coaching_style.data == 'TCAP' else None,
            coaching_subject=form.coaching_subject.data, coach_notes=form.coach_notes.data,
            leitfaden_begruessung=form.leitfaden_begruessung.data,
            leitfaden_legitimation=form.leitfaden_legitimation.data,
            leitfaden_pka=form.leitfaden_pka.data, leitfaden_kek=form.leitfaden_kek.data,
            leitfaden_angebot=form.leitfaden_angebot.data,
            leitfaden_zusammenfassung=form.leitfaden_zusammenfassung.data,
            leitfaden_kzb=form.leitfaden_kzb.data, performance_mark=form.performance_mark.data,
            time_spent=form.time_spent.data
        )
        db.session.add(coaching)
        db.session.commit()
        flash('Coaching erfolgreich gespeichert!', 'success')
        return redirect(url_for('main.index'))
    tcap_js = """
    document.addEventListener('DOMContentLoaded', function() {
        var styleSelect = document.getElementById('coaching_style');
        var tcapIdField = document.getElementById('tcap_id_field');
        function toggleTcapField() {
            if (styleSelect && tcapIdField) { // Zusätzlicher Check
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

# app/main_routes.py
# ...

# Route umbenannt, um beide Rollen abzudecken
@bp.route('/coaching_review_dashboard', methods=['GET', 'POST']) # Neuer, generischerer URL-Pfad
@login_required
@role_required([ROLE_PROJEKTLEITER, ROLE_QM]) # Zugriff für beide Rollen
def pl_qm_dashboard(): # Neuer Funktionsname
    page = request.args.get('page', 1, type=int)
    coachings_query = Coaching.query.order_by(desc(Coaching.coaching_date))
    coachings_paginated = coachings_query.paginate(page=page, per_page=10, error_out=False)
    
    note_form_display = ProjectLeaderNoteForm() 

    dashboard_title = "Review Dashboard" # Standardtitel
    if current_user.role == ROLE_PROJEKTLEITER:
        dashboard_title = "Projektleiter Dashboard"
    elif current_user.role == ROLE_QM:
        dashboard_title = "Quality Coach Dashboard" # Deutscher Titel

    if request.method == 'POST' and 'submit_note' in request.form:
        form_to_validate = ProjectLeaderNoteForm(request.form) 
        coaching_id_str = request.form.get('coaching_id')
        form_errors = False
        if not coaching_id_str:
            flash("Coaching-ID fehlt oder konnte nicht übermittelt werden.", 'danger')
            form_errors = True
        if not form_to_validate.validate():
            for fieldName, errorMessages in form_to_validate.errors.items():
                for err in errorMessages:
                    flash(f"Validierungsfehler im Feld '{form_to_validate[fieldName].label.text}': {err}", 'danger')
            form_errors = True

        if not form_errors:
            notes_data = form_to_validate.notes.data
            try:
                coaching_id_int = int(coaching_id_str)
                coaching_to_update = Coaching.query.get_or_404(coaching_id_int)
                # Hier könnten wir später unterscheiden, wer die Notiz geschrieben hat, falls nötig
                # Für jetzt überschreibt der QM die PL-Notiz und umgekehrt.
                coaching_to_update.project_leader_notes = notes_data # Feld bleibt dasselbe
                db.session.commit()
                flash(f'Notiz für Coaching ID {coaching_id_int} erfolgreich gespeichert.', 'success')
            except ValueError:
                flash('Ungültige Coaching-ID erhalten.', 'danger')
            except Exception as e:
                db.session.rollback()
                flash(f'Fehler beim Speichern der Notiz: {str(e)}', 'danger')
            # Nach dem POST zum selben Dashboard zurückleiten
            return redirect(url_for('main.pl_qm_dashboard', page=request.args.get('page', 1, type=int)))
        else:
            return redirect(url_for('main.pl_qm_dashboard', page=page))

    # Top/Flop Teams Logik (bleibt gleich)
    all_teams_data = []
    teams_list = Team.query.all()
    for team_obj in teams_list: 
        team_stats = db.session.query(
            func.coalesce(func.avg(Coaching.performance_mark * 10.0), 0).label('avg_performance_mark_scaled'), 
            func.coalesce(func.sum(Coaching.time_spent), 0).label('total_time'),
            func.coalesce(func.count(Coaching.id), 0).label('num_coachings')
        ).join(TeamMember, Coaching.team_member_id == TeamMember.id)\
         .filter(TeamMember.team_id == team_obj.id).first()
        if team_stats:
            all_teams_data.append({
                'id': team_obj.id, 'name': team_obj.name,
                'num_coachings': team_stats.num_coachings,
                'avg_score': round(team_stats.avg_performance_mark_scaled, 2), 
                'total_time': team_stats.total_time if team_stats.total_time else 0
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
        'main/projektleiter_dashboard.html', # Wir verwenden dasselbe Template
        title=dashboard_title, # Dynamischer Titel
        coachings_paginated=coachings_paginated, 
        note_form=note_form_display,
        top_3_teams=top_3_teams, 
        flop_3_teams=flop_3_teams
    )
