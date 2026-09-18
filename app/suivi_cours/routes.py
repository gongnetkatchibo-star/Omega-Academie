from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models.classe import Classe
from app.models.suivi_cours import SuiviCours
from app.suivi_cours import suivi_cours_bp
from app.utils import roles_required
from app.services.cycles import cycle_du_role, classe_dans_le_cycle

ROLES_SUPERVISION = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "responsable_pedagogique"]


@suivi_cours_bp.route("/")
@login_required
@roles_required(*ROLES_SUPERVISION, module="suivi_cours")
def tableau():
    """Vue d'ensemble pour la direction : tous les suivis, retards en tête (Module 5)."""
    suivis = SuiviCours.query.order_by(SuiviCours.en_retard.desc(), SuiviCours.date_maj.desc()).all()
    cycle = cycle_du_role(current_user.role)
    if cycle:
        suivis = [s for s in suivis if classe_dans_le_cycle(s.classe, cycle)]
    return render_template("suivi_cours/tableau.html", suivis=suivis)


@suivi_cours_bp.route("/classe/<int:classe_id>", methods=["GET", "POST"])
@login_required
@roles_required("enseignant", *ROLES_SUPERVISION)
def classe(classe_id):
    classe_obj = Classe.query.get_or_404(classe_id)
    cycle = cycle_du_role(current_user.role)
    if cycle and not classe_dans_le_cycle(classe_obj, cycle):
        flash("Cette classe ne relève pas de ton cycle.", "error")
        return redirect(url_for("suivi_cours.tableau"))
    profil = current_user.profil_enseignant if current_user.role == "enseignant" else None
    matieres = None

    if current_user.role == "enseignant":
        matieres = [a.matiere for a in profil.affectations if a.classe_id == classe_id] if profil else []
        if not matieres:
            flash("Vous n'enseignez pas dans cette classe.", "error")
            return redirect(url_for("classes.liste"))

    if request.method == "POST" and current_user.role == "enseignant":
        matiere = request.form.get("matiere")
        chapitre = request.form.get("chapitre", "").strip()
        pourcentage = request.form.get("pourcentage", type=int) or 0
        en_retard = bool(request.form.get("en_retard"))
        difficultes = request.form.get("difficultes", "").strip()

        if matiere not in matieres or not chapitre:
            flash("Merci de choisir une matière que vous enseignez et de préciser le chapitre.", "error")
        else:
            db.session.add(SuiviCours(
                classe_id=classe_id, enseignant_id=profil.id, matiere=matiere,
                chapitre=chapitre, pourcentage=max(0, min(100, pourcentage)),
                en_retard=en_retard, difficultes=difficultes or None,
            ))
            db.session.commit()
            flash("Progression enregistrée.", "info")
        return redirect(url_for("suivi_cours.classe", classe_id=classe_id))

    historique = SuiviCours.query.filter_by(classe_id=classe_id).order_by(SuiviCours.date_maj.desc()).all()
    return render_template("suivi_cours/classe.html", classe=classe_obj, matieres=matieres, historique=historique)
