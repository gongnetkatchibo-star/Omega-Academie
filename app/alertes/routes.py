from flask import render_template
from flask_login import login_required, current_user

from app.models.eleve import Eleve
from app.services.alertes import eleves_absences_frequentes, eleves_moyenne_faible, SEUIL_ABSENCES_INJUSTIFIEES
from app.services.cycles import cycle_du_role, classe_dans_le_cycle
from app.alertes import alertes_bp
from app.utils import roles_required

ROLES_ACCES = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "responsable_pedagogique", "secretaire"]


@alertes_bp.route("/")
@login_required
@roles_required(*ROLES_ACCES, module="alertes")
def tableau():
    annee = Eleve.annee_scolaire_courante()
    eleves = Eleve.query.filter_by(actif=True).all()

    cycle = cycle_du_role(current_user.role)
    if cycle:
        eleves = [e for e in eleves if classe_dans_le_cycle(e.classe, cycle)]

    return render_template(
        "alertes/tableau.html",
        absences=eleves_absences_frequentes(eleves),
        moyennes_faibles=eleves_moyenne_faible(eleves, annee),
        seuil_absences=SEUIL_ABSENCES_INJUSTIFIEES,
    )
