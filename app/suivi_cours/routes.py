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
    """Vue d'ensemble pour la direction : le dernier état de chaque
    matière de chaque classe de l'année, retards en tête (Module 5). Une
    ancienne ligne « en retard » corrigée depuis n'apparaît plus."""
    from app.models.eleve import Eleve

    suivis = (
        SuiviCours.query.join(Classe, SuiviCours.classe_id == Classe.id)
        .filter(Classe.annee_scolaire == Eleve.annee_scolaire_courante())
        .order_by(SuiviCours.date_maj.desc(), SuiviCours.id.desc()).all()
    )
    derniers = {}
    for s in suivis:
        derniers.setdefault((s.classe_id, s.matiere), s)
    suivis = sorted(derniers.values(), key=lambda s: (not s.en_retard, s.classe.niveau, s.classe.nom, s.matiere))
    cycle = cycle_du_role(current_user.role)
    if cycle:
        suivis = [s for s in suivis if classe_dans_le_cycle(s.classe, cycle)]
    return render_template("suivi_cours/tableau.html", suivis=suivis)


@suivi_cours_bp.route("/classe/<int:classe_id>", methods=["GET", "POST"])
@login_required
@roles_required("enseignant", *ROLES_SUPERVISION, module="suivi_cours")
def classe(classe_id):
    classe_obj = db.get_or_404(Classe, classe_id)
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
        chapitre = request.form.get("chapitre", "").strip()[:150]
        pourcentage = request.form.get("pourcentage", type=int) or 0
        en_retard = bool(request.form.get("en_retard"))
        difficultes = request.form.get("difficultes", "").strip()[:1000]

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


@suivi_cours_bp.route("/<int:suivi_id>/supprimer", methods=["POST"])
@login_required
@roles_required("enseignant", *ROLES_SUPERVISION, module="suivi_cours")
def supprimer(suivi_id):
    """Retirer une ligne saisie par erreur : son auteur ou la direction."""
    from flask import abort

    suivi = db.get_or_404(SuiviCours, suivi_id)
    profil = current_user.profil_enseignant if current_user.role == "enseignant" else None
    if current_user.role == "enseignant" and (not profil or suivi.enseignant_id != profil.id):
        abort(403)
    cycle = cycle_du_role(current_user.role)
    if cycle and not classe_dans_le_cycle(suivi.classe, cycle):
        abort(403)
    classe_id = suivi.classe_id
    db.session.delete(suivi)
    db.session.commit()
    flash("Ligne de suivi retirée.", "info")
    return redirect(url_for("suivi_cours.classe", classe_id=classe_id))
