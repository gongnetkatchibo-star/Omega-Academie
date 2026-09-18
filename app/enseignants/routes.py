from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models.user import User
from app.models.classe import Classe
from app.models.enseignant import Enseignant, Affectation
from app.enseignants import enseignants_bp
from app.utils import roles_required, export_csv, export_xlsx, export_pdf_liste
from app.services.cycles import cycle_du_role, classe_dans_le_cycle

ROLES_GESTION = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general", "responsable_pedagogique"]
ROLES_LECTURE = ROLES_GESTION + ["enseignant"]


def _enseigne_dans_le_cycle(enseignant, cycle):
    return cycle is None or any(classe_dans_le_cycle(a.classe, cycle) for a in enseignant.affectations)


@enseignants_bp.route("/")
@login_required
@roles_required(*ROLES_LECTURE)
def liste():
    tous = sorted(Enseignant.query.all(), key=lambda e: e.nom_complet)
    cycle = cycle_du_role(current_user.role)
    if cycle:
        # Un directeur de cycle ne voit que les enseignants intervenant
        # dans au moins une classe de son cycle (document complémentaire, §5).
        tous = [e for e in tous if _enseigne_dans_le_cycle(e, cycle)]
    return render_template("enseignants/liste.html", enseignants=tous)


def _lignes_export_enseignants():
    tous = sorted(Enseignant.query.all(), key=lambda e: e.nom_complet)
    entetes = ["Nom complet", "Email", "Spécialité", "Classes / matières"]
    lignes = [
        (
            e.nom_complet, e.user.email, e.specialite or "—",
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

        if not user_id:
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
@roles_required(*ROLES_LECTURE)
def detail(enseignant_id):
    enseignant = Enseignant.query.get_or_404(enseignant_id)
    classes = Classe.query.order_by(Classe.niveau).all()
    return render_template("enseignants/detail.html", enseignant=enseignant, classes=classes)


@enseignants_bp.route("/<int:enseignant_id>/affecter", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="enseignants")
def affecter(enseignant_id):
    enseignant = Enseignant.query.get_or_404(enseignant_id)
    classe_id = request.form.get("classe_id", type=int)
    matiere = request.form.get("matiere", "").strip()

    if not classe_id or not matiere:
        flash("Merci de choisir une classe et une matière.", "error")
    else:
        db.session.add(Affectation(enseignant_id=enseignant.id, classe_id=classe_id, matiere=matiere))
        db.session.commit()
        flash("Affectation ajoutée.", "info")

    return redirect(url_for("enseignants.detail", enseignant_id=enseignant.id))
