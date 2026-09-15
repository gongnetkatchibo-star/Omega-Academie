from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.classe import Classe
from app.models.eleve import Eleve
from app.models.absence import Absence
from app.absences import absences_bp
from app.utils import roles_required
from app.services.cycles import cycle_du_role, classe_dans_le_cycle

ROLES_SUPERVISION = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "responsable_pedagogique", "secretaire"]


@absences_bp.route("/classe/<int:classe_id>", methods=["GET", "POST"])
@login_required
@roles_required("enseignant")
def saisie(classe_id):
    classe_obj = Classe.query.get_or_404(classe_id)
    profil = current_user.profil_enseignant
    enseigne_ici = profil and any(a.classe_id == classe_id for a in profil.affectations)
    if not enseigne_ici:
        flash("Vous n'enseignez pas dans cette classe.", "error")
        return redirect(url_for("classes.liste"))

    eleves = Eleve.query.filter_by(classe_id=classe_id, actif=True).order_by(Eleve.nom_complet).all()
    date_str = request.args.get("date") or request.form.get("date") or datetime.utcnow().date().isoformat()
    try:
        date_selectionnee = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        date_selectionnee = datetime.utcnow().date()

    absences_existantes = {
        a.eleve_id: a for a in Absence.query.filter_by(classe_id=classe_id, date=date_selectionnee).all()
    }

    if request.method == "POST":
        for eleve in eleves:
            est_absent = request.form.get(f"absent_{eleve.id}") == "on"
            justifiee = request.form.get(f"justifiee_{eleve.id}") == "on"
            motif = request.form.get(f"motif_{eleve.id}", "").strip()
            existante = absences_existantes.get(eleve.id)

            if est_absent:
                if existante:
                    existante.justifiee = justifiee
                    existante.motif = motif or None
                else:
                    db.session.add(Absence(
                        eleve_id=eleve.id, classe_id=classe_id, date=date_selectionnee,
                        justifiee=justifiee, motif=motif or None, enseignant_id=profil.id,
                    ))
            elif existante:
                # Décoché après avoir été marqué absent : on corrige, on ne
                # laisse pas une absence fantôme.
                db.session.delete(existante)

        db.session.commit()
        flash(f"Absences enregistrées pour le {date_selectionnee.strftime('%d/%m/%Y')}.", "info")
        return redirect(url_for("absences.saisie", classe_id=classe_id, date=date_selectionnee.isoformat()))

    return render_template(
        "absences/saisie.html", classe=classe_obj, eleves=eleves,
        date_selectionnee=date_selectionnee, absences_existantes=absences_existantes,
    )


@absences_bp.route("/eleve/<int:eleve_id>")
@login_required
def historique(eleve_id):
    eleve = Eleve.query.get_or_404(eleve_id)

    est_lie_comme_parent = current_user in eleve.parents
    est_soi_meme = current_user.role == "eleve" and eleve.user_id == current_user.id
    est_enseignant_de_la_classe = (
        current_user.role == "enseignant" and current_user.profil_enseignant
        and any(a.classe_id == eleve.classe_id for a in current_user.profil_enseignant.affectations)
    )
    cycle = cycle_du_role(current_user.role)
    from app.services.permissions import role_a_acces
    est_supervision = role_a_acces(current_user.role, "absences", ROLES_SUPERVISION) and (not cycle or classe_dans_le_cycle(eleve.classe, cycle))

    if not (est_lie_comme_parent or est_soi_meme or est_enseignant_de_la_classe or est_supervision or current_user.role == "developpeur"):
        abort(403)

    absences = Absence.query.filter_by(eleve_id=eleve_id).order_by(Absence.date.desc()).all()
    nb_injustifiees = sum(1 for a in absences if not a.justifiee)
    return render_template(
        "absences/historique.html", eleve=eleve, absences=absences, nb_injustifiees=nb_injustifiees,
    )
