from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import User, Team, TeamMember, Coaching
from app.forms import CoachingForm, ProjectLeaderNoteForm
from app.utils import role_required, ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_TEAMLEITER
from sqlalchemy import desc # Für Sortierung

bp = Blueprint('main', __name__)

@bp.route('/')
@bp.route('/index')
@login_required
def index():
    """ "Complete View" - Zeigt alle Coachings an, mit erweiterten Rechten.
        Teamleiter sehen nur Coachings ihres Teams.
    """
    page = request.args.get('page', 1, type=int)
    
    if current_user.role in [ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER]:
        coachings_query = Coaching.query
    elif current_user.role == ROLE_TEAMLEITER:
        if not current_user.team_id:
            flash("Ihnen ist kein Team zugewiesen. Bitte kontaktieren Sie einen Admin.", "warning")
            return render_template('main/index.html', title='Dashboard', coachings_paginated=None, total_coachings=0)
        
        # Teamleiter sieht Coachings, die von ihm durchgeführt wurden ODER für Mitglieder seines Teams sind
        team_members_ids = [member.id for member in TeamMember.query.filter_by(team_id=current_user.team_id).all()]
        if not team_members_ids: # Kein Mitglied im Team
             coachings_query = Coaching.query.filter(Coaching.coach_id == current_user.id) # Nur eigene Coachings
        else: # Coachings für eigene Teammitglieder ODER von sich selbst durchgeführt
            coachings_query = Coaching.query.filter(
                (Coaching.team_member_id.in_(team_members_ids)) | (Coaching.coach_id == current_user.id)
            )
    else: # Sollte nicht passieren, wenn Rollen korrekt gesetzt sind
        abort(403)

    coachings_paginated = coachings_query.order_by(desc(Coaching.coaching_date)).paginate(page=page, per_page=10, error_out=False)
    total_coachings = coachings_query.count()
    
    return render_template('main/index.html', title='Dashboard - Alle Coachings',
                           coachings_paginated=coachings_paginated, total_coachings=total_coachings)


@bp.route('/team_view')
@login_required
@role_required([ROLE_TEAMLEITER, ROLE_ADMIN, ROLE_PROJEKTLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER])
def team_view():
    """
    Zeigt Details für das Team eines Teamleiters.
    Andere berechtigte Rollen können ein Team auswählen (TODO: Implementierung für Auswahl).
    Fürs Erste: Teamleiter sieht sein Team, andere sehen eine Übersicht oder das erste Team.
    """
    team = None
    team_coachings = None
    team_members_performance = []

    if current_user.role == ROLE_TEAMLEITER:
        if not current_user.team_id:
            flash("Ihnen ist kein Team zugewiesen.", "warning")
            return redirect(url_for('main.index'))
        team = Team.query.get(current_user.team_id)
        if not team:
            flash("Zugehöriges Team nicht gefunden.", "danger")
            return redirect(url_for('main.index'))
    else:
        # Für andere Rollen: ggf. Auswahl ermöglichen oder erstes Team anzeigen
        # Hier erstmal eine einfache Logik: Zeige erstes Team
        team = Team.query.first()
        if not team:
            flash("Keine Teams im System vorhanden.", "info")
            return render_template('main/team_view.html', title='Team Ansicht', team=None)
            
    if team:
        team_member_ids = [member.id for member in team.members]
        # Coachings, bei denen das Teammitglied aus dem aktuellen Team ist
        team_coachings_query = Coaching.query.filter(Coaching.team_member_id.in_(team_member_ids))
        team_coachings = team_coachings_query.order_by(desc(Coaching.coaching_date)).limit(20).all() # Letzte 20 Coachings

        # Performance der Teammitglieder (Durchschnittsscores)
        for member in team.members:
            member_coachings = member.coachings_received.all()
            if member_coachings:
                avg_score = sum(c.overall_score for c in member_coachings) / len(member_coachings)
                total_time = sum(c.time_spent for c in member_coachings if c.time_spent)
            else:
                avg_score = 0
                total_time = 0
            team_members_performance.append({
                'name': member.name,
                'avg_score': round(avg_score, 2),
                'total_coachings': len(member_coachings),
                'total_coaching_time': total_time
            })

    return render_template('main/team_view.html', title=f'Team Ansicht: {team.name if team else "Kein Team"}',
                           team=team, team_coachings=team_coachings,
                           team_members_performance=team_members_performance)


@bp.route('/coaching/add', methods=['GET', 'POST'])
@login_required
@role_required([ROLE_TEAMLEITER, ROLE_QM, ROLE_SALESCOACH, ROLE_TRAINER, ROLE_ADMIN]) # Admin kann auch Coachings hinzufügen
def add_coaching():
    # Übergebe Rolle und TeamID des aktuellen Benutzers an das Formular,
    # damit es die Auswahl der Teammitglieder entsprechend filtern kann.
    form = CoachingForm(current_user_role=current_user.role, current_user_team_id=current_user.team_id)

    if form.validate_on_submit():
        coaching = Coaching(
            team_member_id=form.team_member_id.data,
            coach_id=current_user.id, # Der eingeloggte Benutzer ist der Coach
            coaching_style=form.coaching_style.data,
            tcap_id=form.tcap_id.data if form.coaching_style.data == 'TCAP' else None,
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
        return redirect(url_for('main.index'))
    
    # JavaScript, um TCAP ID Feld ein-/auszublenden
    tcap_js = """
    document.addEventListener('DOMContentLoaded', function() {
        var styleSelect = document.getElementById('coaching_style');
        var tcapIdField = document.getElementById('tcap_id_field'); // Wrapper div
        
        function toggleTcapField() {
            if (styleSelect.value === 'TCAP') {
                tcapIdField.style.display = '';
            } else {
                tcapIdField.style.display = 'none';
                document.getElementById('tcap_id').value = ''; // Feld leeren, wenn nicht TCAP
            }
        }
        
        if(styleSelect && tcapIdField) {
            styleSelect.addEventListener('change', toggleTcapField);
            toggleTcapField(); // Initial check on page load
        }
    });
    """
    return render_template('main/add_coaching.html', title='Coaching hinzufügen', form=form, tcap_js=tcap_js)


@bp.route('/projektleiter_dashboard', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_PROJEKTLEITER)
def projektleiter_dashboard():
    page = request.args.get('page', 1, type=int)
    coachings_paginated = Coaching.query.order_by(desc(Coaching.coaching_date)).paginate(page=page, per_page=10, error_out=False)
    
    note_form = ProjectLeaderNoteForm()

    if note_form.validate_on_submit() and 'submit_note' in request.form : # Name des Submit-Buttons prüfen
        coaching_id = note_form.coaching_id.data
        coaching_to_update = Coaching.query.get_or_404(coaching_id)
        coaching_to_update.project_leader_notes = note_form.notes.data
        db.session.commit()
        flash(f'Notiz für Coaching ID {coaching_id} gespeichert.', 'success')
        return redirect(url_for('main.projektleiter_dashboard', page=page)) # Bleibe auf der aktuellen Seite

    return render_template('main/projektleiter_dashboard.html', title='Projektleiter Dashboard',
                           coachings_paginated=coachings_paginated, note_form=note_form)