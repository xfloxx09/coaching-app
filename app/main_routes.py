# app/main_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import User, Team, TeamMember, Coaching
from app.forms import CoachingForm, ProjectLeaderNoteForm 
from app.utils import role_required, ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_TEAMLEITER
from sqlalchemy import desc, func 
from datetime import datetime, timedelta
import sqlalchemy # Für sqlalchemy.sql.false()

bp = Blueprint('main', __name__)

# ... (deine index, team_view, add_coaching Routen bleiben wie sie waren) ...
@bp.route('/')
@bp.route('/index')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
        coachings_query = Coaching.query
    elif current_user.role == ROLE_TEAMLEITER:
        if not current_user.team_id_if_leader:
            flash("Ihnen ist kein Team zugewiesen. Bitte kontaktieren Sie einen Admin.", "warning")
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
        coachings_query = Coaching.query.filter(sqlalchemy.sql.false())
    coachings_paginated = coachings_query.order_by(desc(Coaching.coaching_date)).paginate(page=page, per_page=10, error_out=False)
    total_coachings = coachings_query.count()
    return render_template('main/index.html', title='Dashboard - Alle Coachings',
                           coachings_paginated=coachings_paginated, total_coachings=total_coachings)

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
    tcap_js = """...""" # Dein tcap_js bleibt hier
    return render_template('main/add_coaching.html', title='Coaching hinzufügen', form=form, tcap_js=tcap_js)

@bp.route('/projektleiter_dashboard', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_PROJEKTLEITER)
def projektleiter_dashboard():
    page = request.args.get('page', 1, type=int)
    coachings_query = Coaching.query.order_by(desc(Coaching.coaching_date))
    coachings_paginated = coachings_query.paginate(page=page, per_page=10, error_out=False)
    
    # Diese Instanz wird für die Anzeige im Template verwendet (rendert CSRF, wenn hidden_tag() genutzt wird)
    note_form_display = ProjectLeaderNoteForm() 

    if request.method == 'POST' and 'submit_note' in request.form:
        print("DEBUG PL_DASH: POST-Request für 'submit_note' erhalten.")
        print(f"DEBUG PL_DASH: request.form enthält: {request.form}")

        # Formular nur für die Validierung der 'notes' und CSRF
        form_for_validation = ProjectLeaderNoteForm(request.form) 
        
        coaching_id_str = request.form.get('coaching_id') # Hole coaching_id manuell
        
        # Manuelle Prüfung für coaching_id
        form_errors = False
        if not coaching_id_str:
            flash("Coaching-ID fehlt oder konnte nicht übermittelt werden.", 'danger')
            print("DEBUG PL_DASH: coaching_id_str ist leer oder None.")
            form_errors = True
        
        # Validiere das Formular (prüft 'notes' und CSRF)
        if not form_for_validation.validate():
            print("DEBUG PL_DASH: form_for_validation Validierung fehlgeschlagen.")
            for fieldName, errorMessages in form_for_validation.errors.items():
                for err in errorMessages:
                    label_text = fieldName
                    try:
                        label_text = form_for_validation[fieldName].label.text
                    except: pass
                    print(f"DEBUG PL_DASH: Fehler im Feld '{label_text}': {err}")
                    flash(f"Validierungsfehler im Feld '{label_text}': {err}", 'danger')
            form_errors = True

        if not form_errors: # Wenn keine manuellen Fehler UND keine Formularfehler
            notes_data = form_for_validation.notes.data # oder direkt request.form.get('notes')
            print(f"DEBUG PL_DASH: Validierung erfolgreich. Coaching ID: {coaching_id_str}, Notes: {notes_data[:50]}...")
            
            try:
                coaching_id_int = int(coaching_id_str) # Konvertiere zu int für die Query
                coaching_to_update = Coaching.query.get_or_404(coaching_id_int)
                coaching_to_update.project_leader_notes = notes_data
                db.session.commit()
                flash(f'Notiz für Coaching ID {coaching_id_int} erfolgreich gespeichert.', 'success')
                print(f"DEBUG PL_DASH: Notiz für Coaching {coaching_id_int} commited.")
            except ValueError:
                flash('Ungültige Coaching-ID erhalten.', 'danger')
                print(f"FEHLER: Ungültige Coaching-ID: {coaching_id_str}")
            except Exception as e:
                db.session.rollback()
                flash(f'Fehler beim Speichern der Notiz: {str(e)}', 'danger')
                print(f"FEHLER DB Commit PL Notiz: {e}")
                import traceback
                traceback.print_exc()
            
            return redirect(url_for('main.projektleiter_dashboard', page=request.args.get('page', 1, type=int)))
        else:
            # Bei Validierungsfehlern einfach zur Seite zurückleiten, Flash-Nachrichten werden angezeigt
            return redirect(url_for('main.projektleiter_dashboard', page=page))

    return render_template(
        'main/projektleiter_dashboard.html', 
        title='Projektleiter Dashboard',
        coachings_paginated=coachings_paginated, 
        note_form=note_form_display 
    )
