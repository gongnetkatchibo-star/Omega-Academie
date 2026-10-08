"""Cahier de textes et devoirs : l'enseignant note ce qu'il a fait en
classe et le travail à faire ; la direction suit ; la famille voit les
devoirs de l'enfant."""

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.cahier_textes import cahier_textes_bp
from app.models.cahier_textes import SeanceCahier
from app.models.classe import Classe
from app.models.eleve import Eleve
from app.services.cycles import cycle_du_role, filtrer_par_cycle
from app.services.suivi_eleve import (
    DIRECTION, classes_de_l_enseignant, matieres_dans, supervise, peut_suivre, date_du_formulaire,
)
from app.services.temps import aujourd_hui
from app.services.pagination import paginer

ROLES_SUPERVISION = DIRECTION + ["responsable_pedagogique"]
MODULE = "cahier_textes"


@cahier_textes_bp.route("/")
@login_required
def index():
    """Choix de la classe : celles de l'enseignant, ou toutes (cycle
    compris) pour la direction."""
    from app.services.permissions import role_a_acces

    annee = Eleve.annee_scolaire_courante()
    classes = Classe.query.filter_by(annee_scolaire=annee).order_by(Classe.niveau, Classe.nom).all()
    if current_user.role == "enseignant":
        mes_classes = classes_de_l_enseignant()
        classes = [c for c in classes if c.id in mes_classes]
    elif current_user.role == "developpeur" or role_a_acces(current_user.role, MODULE, ROLES_SUPERVISION):
        classes = filtrer_par_cycle(classes, cycle_du_role(current_user.role))
    else:
        abort(403)
    return render_template(
        "classes/choisir.html", classes=classes, titre="Cahier de textes", icone_cle="cahier_textes",
        endpoint="cahier_textes.classe", libelle="Ouvrir le cahier",
    )


@cahier_textes_bp.route("/classe/<int:classe_id>", methods=["GET", "POST"])
@login_required
def classe(classe_id):
    classe_obj = db.get_or_404(Classe, classe_id)
    matieres = matieres_dans(classe_id)
    if not matieres and not supervise(classe_obj, MODULE, ROLES_SUPERVISION):
        abort(403)

    if request.method == "POST":
        if not matieres:
            abort(403)
        matiere = request.form.get("matiere", "")
        contenu = request.form.get("contenu", "").strip()
        devoir = request.form.get("devoir", "").strip()
        date_seance = date_du_formulaire("date")
        date_rendu = date_du_formulaire("date_rendu", facultative=True)
        if matiere not in matieres or not contenu:
            flash("Choisis une de tes matières et décris la séance.", "error")
        elif date_rendu and date_rendu < date_seance:
            flash("La date de remise du devoir ne peut pas précéder la séance.", "error")
        else:
            db.session.add(SeanceCahier(
                classe_id=classe_id, enseignant_id=current_user.profil_enseignant.id, matiere=matiere,
                date=date_seance, contenu=contenu[:4000], devoir=devoir[:2000] or None,
                date_rendu=date_rendu if devoir else None,
            ))
            db.session.commit()
            flash("Séance ajoutée au cahier de textes.", "info")
        return redirect(url_for("cahier_textes.classe", classe_id=classe_id))

    from app.models.enseignant import Enseignant
    page = paginer(
        SeanceCahier.query.options(db.joinedload(SeanceCahier.enseignant).joinedload(Enseignant.user))
        .filter_by(classe_id=classe_id)
        .order_by(SeanceCahier.date.desc(), SeanceCahier.id.desc())
    )
    return render_template(
        "cahier_textes/classe.html", classe=classe_obj, matieres=matieres, page=page,
        aujourd_hui=aujourd_hui(),
    )


@cahier_textes_bp.route("/seance/<int:seance_id>/supprimer", methods=["POST"])
@login_required
def supprimer(seance_id):
    seance = db.get_or_404(SeanceCahier, seance_id)
    profil = current_user.profil_enseignant if current_user.role == "enseignant" else None
    est_auteur = profil is not None and seance.enseignant_id == profil.id
    if not (est_auteur or supervise(seance.classe, MODULE, ROLES_SUPERVISION)):
        abort(403)
    classe_id = seance.classe_id
    db.session.delete(seance)
    db.session.commit()
    flash("Séance retirée du cahier de textes.", "info")
    return redirect(url_for("cahier_textes.classe", classe_id=classe_id))


@cahier_textes_bp.route("/eleve/<int:eleve_id>")
@login_required
def eleve(eleve_id):
    """Devoirs à faire et dernières séances de la classe d'un élève —
    pour ses parents, lui-même, ses enseignants et la direction."""
    eleve_obj = db.get_or_404(Eleve, eleve_id)
    if not peut_suivre(eleve_obj, MODULE, ROLES_SUPERVISION):
        abort(403)
    jour = aujourd_hui()
    base = SeanceCahier.query.filter_by(classe_id=eleve_obj.classe_id)
    devoirs = (
        base.filter(SeanceCahier.devoir.isnot(None), SeanceCahier.date_rendu >= jour)
        .order_by(SeanceCahier.date_rendu, SeanceCahier.matiere).all()
    )
    seances = base.order_by(SeanceCahier.date.desc(), SeanceCahier.id.desc()).limit(30).all()
    return render_template(
        "cahier_textes/eleve.html", eleve=eleve_obj, devoirs=devoirs, seances=seances, aujourd_hui=jour,
    )
