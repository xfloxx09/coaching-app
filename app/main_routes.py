# app/main_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db # db importieren
from app.models import User, Team, TeamMember, Coaching # Modelle importieren
from app.forms import CoachingForm, ProjectLeaderNoteForm # Formulare importieren
from app.utils import role_required, ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_TEAMLEITER
from sqlalchemy import desc, func # func für spätere Aggregationen
from datetime import datetime, timedelta # Für Zeitfilter, falls später benötigt

bp = Blueprint('main', __name__)

# Hilfsfunktion (kann später für Dashboard-Filter nützlich sein)
def get_filtered_coachings_query(days_filter=None, team_id_filter=None, current_user_for_tl_filter=None):
    base_query = Coaching.query

    if days_filter:
        try:
            start_date = datetime.utcnow() - timedelta(days=int(days_filter))
            base_query = base_query.filter(Coaching.coaching_date >= start_date)
        except ValueError:
            pass # Ungültiger days_filter wird ignoriert

    if team_id_filter and team_id_filter != "all":
        try:
            team_member_ids_for_team = [
                member.id for member in TeamMember.query.filter_by(team_id=int(team_id_filter)).all()
            ]
            base_query = base_query.filter(Coaching.team_member_id.in_(team_member_ids_for_team))
        except ValueError:
            pass # Ungültiger team_id_filter wird ignoriert
    
    elif current_user_for_tl_filter and current_user_for_tl_filter.role == ROLE_TEAMLEITER:
        if current_user_for_tl_filter.team_id_if_leader:
            team_members_ids = [
                member.id for member in TeamMember.query.filter_by(team_id=current_user_for_tl_filter.team_id_if_leader).all()
            ]
            if team_members_ids:
                base_query = base_query.filter(
                    (Coaching.team_member_id.in_(team_members_ids)) | (Coaching.coach_id == current_user_for_tl_filter.id)
                )
            else:
                base_query = base_query.filter(Coaching.coach_id == current_user_for_tl_filter.id)
        else:
            import sqlalchemy # Import für sqlalchemy.sql.false()
            base_query = base_query.filter(sqlalchemy.sql.false())
            
    return base_query


@bp.route('/')
@bp.route('/index')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    
    # Basis-Query basierend auf Rolle
    if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
        coachings_query = Coaching.query
    elif current_user.role == ROLE_TEAMLEITER:
        if not current_user.team_id_if_leader:
            flash("Ihnen ist kein Team zugewiesen. Bitte kontaktieren Sie einen Admin.", "warning")
            import sqlalchemy # Import für sqlalchemy.sql.false()
            coachings_query = Coaching.query.filter(sqlalchemy.sql.false()) 
        else:
            team_members_ids = [member.id for member in TeamMember.query.filter_by(team_id=current_user.team_id_if_leader).all()]
            if not team_members_ids:
                 coachings_query = Coaching.query.filter(Coaching.coach_id == current_user.id)
            else:
                coachings_query = Coaching.query.filter(
                    (Coaching.team_member_id.in_(team_members_ids)) | (Coaching.coach_id == current_user.id)
                )
    else:
        import sqlalchemy # Import für sqlalchemy.sql.false()
        coachings_query = Coaching.query.filter(sqlalchemy.sql.false())


    coachings_paginated = coachings_query.order_by(desc(Coaching.coaching_date)).paginate(page=page, per_page=10, error_out=False)
    total_coachings = coachings_query.count() # count() auf die Query vor der Paginierung
    
    return render_template('main/index.html', title='Dashboard - Alle Coachings',
                           coachings_paginated=coachings_paginated, total_coachings=total_coachings)


@bp.route('/team_view')
@login_required
@role_required([ROLE_TEAMLEITER, ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER])
def team_view():
    team = None
    team_coachings_list = [] # Geändert zu team_coachings_list um Verwechslung mit Model zu vermeiden
    team_members_performance = []

    view_team_id = request.args.get('team_id', type=int)

    if current_user.role == ROLE_TEAMLEITER and not view_team_id: # Wenn TL und keine team_id übergeben wurde, sein Team nehmen
        if not current_user.team_id_if_leader:
            flash("Ihnen ist kein Team zugewiesen.", "warning")
            return redirect(url_for('main.index'))
        team = Team.query.get(current_user.team_id_if_leader)
    elif view_team_id: # Wenn eine team_id übergeben wurde (z.B. für Admin-Ansicht)
        if current_user.role not in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
            abort(403) # Nur berechtigte Rollen dürfen andere Teams sehen
        team = Team.query.get(view_team_id)
    else: # Fallback für Admins etc., wenn keine team_id übergeben wird: erstes Team
        if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
            team = Team.query.first()
        else: # Sollte nicht passieren
            abort(403)
            
    if not team:
        flash("Team nicht gefunden oder keine Teams im System vorhanden.", "info")
        # Zeige eine Liste aller Teams für berechtigte User, um eines auszuwählen
        all_teams_list = []
        if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
            all_teams_list = Team.query.order_by(Team.name).all()
        return render_template('main/team_view.html', title='Team Ansicht', team=None, all_teams_list=all_teams_list)
            
    if team:
        team_member_ids = [member.id for member in team.members]
        team_coachings_query = Coaching.query.filter(Coaching.team_member_id.in_(team_member_ids))
        team_coachings_list = team_coachings_query.order_by(desc(Coaching.coaching_date)).limit(20).all()

        for member in team.members:
            member_coachings = member.coachings_received.all() # coachings_received ist eine Query, .all() ausführen
            avg_score = sum(c.overall_score for c in member_coachings) / len(member_coachings) if member_coachings else 0
            total_time = sum(c.time_spent for c in member_coachings if c.time_spent)
            team_members_performance.append({
                'name': member.name,
                'avg_score': round(avg_score, 2),
                'total_coachings': len(member_coachings),
                'total_coaching_time': total_time
            })

    # Für Admins etc., um ein anderes Team auszuwählen
    all_teams_list = []
    if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
        all_teams_list = Team.query.order_by(Team.name).all()

    return render_template('main/team_view.html', 
                           title=f'Team Ansicht: {team.name if team else "Kein Team ausgewählt"}',
                           team=team, team_coachings=team_coachings_list, # Korrigierter Variablenname
                           team_members_performance=team_members_performance,
                           all_teams_list=all_teams_list) # Für den Auswahl-Dropdown


@bp.route('/coaching/add', methods=['GET', 'POST'])
@login_required
@role_required([ROLE_TEAMLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_ADMIN])
def add_coaching():
    form = CoachingForm(current_user_role=current_user.role, current_user_team_id=current_user.team_id_if_leader)

    if form.validate_on_submit():
        coaching = Coaching(
            team_member_id=form.team_member_id.data,
            coach_id=current_user.id,
            coaching_style=form.coaching_style.data,
            tcap_id=form.tcap_id.data if form.coaching_style.data == 'TCAP' else None,
            
            coaching_subject=form.coaching_subject.data, # NEUES FELD
            coach_notes=form.coach_notes.data,           # NEUES FELD
            
            leitfaden_begruessung=form.leitfaden_begruessung.data,
            leitfaden_legitimation=form.leitfaden_legitimation.data,
            leitfaden_pka=form.leitfaden_pka.data,
            leitfaden_kek=form.leitfaden_kek.data,
            leitfaden_angebot=form.leitfaden_angebot.data,
            leitfaden_zusammenfassung=form.leitfaden_zusammenfassung.data,
            leitfaden_kzb=form.leitfaden_kzb.data,
            performance_mark=form.performance_mark.data,
            time_spent=form.time_spent.data
        )
        db.session.add(coaching)
        db.session.commit()
        flash('Coaching erfolgreich gespeichert!', 'success')
        return redirect(url_for('main.index')) # Oder zur Team-Ansicht des gecoachten Teams?
    
    tcap_js = """
    document.addEventListener('DOMContentLoaded', function() {
        var styleSelect = document.getElementById('coaching_style');
        var tcapIdField = document.getElementById('tcap_id_field');
        function toggleTcapField() {
            if (styleSelect.value === 'TCAP') {
                tcapIdField.style.display = '';
                document.getElementById('tcap_id').required = true; // TCAP ID wird Pflicht
            } else {
                tcapIdField.style.display = 'none';
                document.getElementById('tcap_id').value = '';
                document.getElementById('tcap_id').required = false; // TCAP ID nicht mehr Pflicht
            }
        }
        if(styleSelect && tcapIdField) {
            styleSelect.addEventListener('change', toggleTcapField);
            toggleTcapField(); 
        }
    });
    """
    return render_template('main/add_coaching.html', title='Coaching hinzufügen', form=form, tcap_js=tcap_js)


@bp.route('/projektleiter_dashboard', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_PROJEKTLEITER)
def projektleiter_dashboard():
    page = request.args.get('page', 1, type=int)
    # Nur Coachings anzeigen, denen noch keine PL-Notiz hinzugefügt wurde oder alle?
    # Hier erstmal alle:
    coachings_paginated = Coaching.query.order_by(desc(Coaching.coaching_date)).paginate(page=page, per_page=10, error_out=False)
    
    note_form = ProjectLeaderNoteForm()

    if note_form.validate_on_submit() and 'submit_note' in request.form :
        coaching_id = note_form.coaching_id.data
        coaching_to_update = Coaching.query.get_or_404(coaching_id)
        coaching_to_update.project_leader_notes = note_form.notes.data
        db.session.commit()
        flash(f'Notiz für Coaching ID {coaching_id} gespeichert.', 'success')
        return redirect(url_for('main.projektleiter_dashboard', page=page))

    return render_template('main/projektleiter_dashboard.html', title='Projektleiter Dashboard',
                           coachings_paginated=coachings_paginated, note_form=note_form)