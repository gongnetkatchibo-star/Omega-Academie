from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models.user import User
from app.models.classe import Classe
from app.models.enseignant import Enseignant, Affectation
from app.enseignants import enseignants_bp
from app.utils import roles_required, export_csv, export_xlsx, export_pdf_liste
from app.services.cycles import cycle_du_role, classe_dans_le_cycle, exiger_classe_du_cycle, filtrer_par_cycle

ROLES_GESTION = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "responsable_pedagogique"]
ROLES_LECTURE = ROLES_GESTION + ["enseignant"]


def _enseigne_dans_le_cycle(enseignant, cycle):
    return cycle is None or any(classe_dans_le_cycle(a.classe, cycle) for a in enseignant.affectations)


@enseignants_bp.route("/")
@login_required
@roles_required(*ROLES_LECTURE, module="enseignants")
def liste():
    # Un directeur de cycle ne voit que les enseignants intervenant dans au
    # moins une classe de son cycle (document complémentaire, §5).
    return render_template("enseignants/liste.html", enseignants=_enseignants_visibles())


def _enseignants_visibles():
    from sqlalchemy.orm import selectinload

    tous = sorted(
        Enseignant.query.options(selectinload(Enseignant.user), selectinload(Enseignant.affectations).selectinload(Affectation.classe)).all(),
        key=lambda e: e.nom_complet,
    )
    cycle = cycle_du_role(current_user.role)
    return [e for e in tous if _enseigne_dans_le_cycle(e, cycle)] if cycle else tous


def _lignes_export_enseignants():
    tous = _enseignants_visibles()
    entetes = ["Nom complet", "Genre", "Email", "Spécialité", "Classes / matières"]
    lignes = [
        (
            e.nom_complet, {"M": "M", "F": "F"}.get(e.user.genre, "—"), e.user.email, e.specialite or "—",
            ", ".join(f"{a.classe.nom} ({a.matiere})" for a in e.affectations) or "Aucune",
        )
        for e in tous
    ]
    return entetes, lignes


@enseignants_bp.route("/export/<fmt>")
@login_required
@roles_required(*ROLES_GESTION, module="enseignants")
def export(fmt):
    entetes, lignes = _lignes_export_enseignants()
    if fmt == "csv":
        return export_csv(entetes, lignes, "enseignants")
    if fmt == "xlsx":
        return export_xlsx(entetes, lignes, "enseignants", "Enseignants")
    if fmt == "pdf":
        return export_pdf_liste("Liste des enseignants", None, entetes, lignes, "enseignants")
    flash("Format d'export inconnu.", "error")
    return redirect(url_for("enseignants.liste"))


@enseignants_bp.route("/nouveau", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="enseignants")
def nouveau():
    ids_avec_profil = [e.user_id for e in Enseignant.query.all()]
    requete = User.query.filter_by(role="enseignant", statut="actif")
    if ids_avec_profil:
        requete = requete.filter(~User.id.in_(ids_avec_profil))
    candidats = requete.order_by(User.nom_complet).all()

    if request.method == "POST":
        user_id = request.form.get("user_id", type=int)
        specialite = request.form.get("specialite", "").strip()

        if not user_id or user_id not in {c.id for c in candidats}:
            flash("Merci de choisir un compte enseignant.", "error")
            return render_template("enseignants/nouveau.html", candidats=candidats)

        enseignant = Enseignant(user_id=user_id, specialite=specialite)
        db.session.add(enseignant)
        db.session.commit()
        flash("Profil enseignant créé.", "info")
        return redirect(url_for("enseignants.detail", enseignant_id=enseignant.id))

    return render_template("enseignants/nouveau.html", candidats=candidats)


@enseignants_bp.route("/<int:enseignant_id>")
@login_required
@roles_required(*ROLES_LECTURE, module="enseignants")
def detail(enseignant_id):
    from flask import abort
    from app.models.eleve import Eleve

    enseignant = db.get_or_404(Enseignant, enseignant_id)
    # Un enseignant ne consulte que sa propre fiche ; un directeur de cycle,
    # celles des enseignants de son cycle (ou sans affectation, pour les affecter).
    if current_user.role == "enseignant" and enseignant.user_id != current_user.id:
        abort(403)
    cycle = cycle_du_role(current_user.role)
    if cycle and enseignant.affectations and not _enseigne_dans_le_cycle(enseignant, cycle):
        abort(403)
    classes = filtrer_par_cycle(
        Classe.query.filter_by(annee_scolaire=Eleve.annee_scolaire_courante()).order_by(Classe.niveau, Classe.nom).all(), cycle,
    )
    return render_template("enseignants/detail.html", enseignant=enseignant, classes=classes)


@enseignants_bp.route("/<int:enseignant_id>/affecter", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="enseignants")
def affecter(enseignant_id):
    enseignant = db.get_or_404(Enseignant, enseignant_id)
    classe_id = request.form.get("classe_id", type=int)
    matiere = request.form.get("matiere", "").strip()

    from app.models.matiere import matiere_acceptee
    from app.services.journal import journaliser

    classe = db.session.get(Classe, classe_id) if classe_id else None
    if not classe or not matiere:
        flash("Merci de choisir une classe et une matière.", "error")
    elif not matiere_acceptee(matiere):
        flash("Cette matière ne fait pas partie de la liste de l'école.", "error")
    else:
        exiger_classe_du_cycle(classe)
        if Affectation.query.filter_by(enseignant_id=enseignant.id, classe_id=classe.id, matiere=matiere).first():
            flash("Cette affectation existe déjà.", "error")
        else:
            db.session.add(Affectation(enseignant_id=enseignant.id, classe_id=classe.id, matiere=matiere[:80]))
            journaliser("affectation_enseignant", details=f"{enseignant.nom_complet} → {classe.nom} ({matiere})")
            db.session.commit()
            flash("Affectation ajoutée.", "info")

    return redirect(url_for("enseignants.detail", enseignant_id=enseignant.id))


@enseignants_bp.route("/affectation/<int:affectation_id>/retirer", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="enseignants")
def retirer_affectation(affectation_id):
    """L'enseignant perd aussitôt l'accès à cette classe pour cette matière
    (notes, appel, cahier de textes). Ce qu'il a déjà saisi reste."""
    from app.services.journal import journaliser

    affectation = db.get_or_404(Affectation, affectation_id)
    exiger_classe_du_cycle(affectation.classe)
    enseignant_id = affectation.enseignant_id
    journaliser("retrait_affectation", details=f"{affectation.enseignant.nom_complet} ← {affectation.classe.nom} ({affectation.matiere})")
    db.session.delete(affectation)
    db.session.commit()
    flash("Affectation retirée.", "info")
    return redirect(url_for("enseignants.detail", enseignant_id=enseignant_id))
