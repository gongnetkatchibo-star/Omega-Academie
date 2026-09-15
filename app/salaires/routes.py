from datetime import datetime

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models.user import User
from app.models.salaire import Salaire, STATUTS_SALAIRE, LIBELLES_STATUT_SALAIRE, MOIS_LIBELLES
from app.models.mouvement_caisse import MouvementCaisse
from app.salaires import salaires_bp
from app.utils import roles_required

ROLES_GESTION = ["comptable", "fondateur", "administrateur_general"]
ROLES_SUPPRESSION = ["fondateur", "administrateur_general"]


@salaires_bp.route("/")
@login_required
@roles_required(*ROLES_GESTION, module="salaires")
def liste():
    salaires = Salaire.query.order_by(Salaire.annee.desc(), Salaire.mois.desc()).all()
    total_paye = sum(s.montant for s in salaires if s.statut == "paye")
    total_impaye = sum(s.montant for s in salaires if s.statut == "impaye")
    return render_template(
        "salaires/liste.html", salaires=salaires, total_paye=total_paye,
        total_impaye=total_impaye, mois_libelles=MOIS_LIBELLES,
    )


@salaires_bp.route("/nouveau", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module="salaires")
def nouveau():
    # Tout compte actif peut être payé ici — pas seulement les enseignants,
    # la direction et le personnel administratif ont aussi un salaire.
    personnel = User.query.filter_by(statut="actif").filter(User.role != "eleve").order_by(User.nom_complet).all()

    if request.method == "POST":
        personnel_id = request.form.get("personnel_id", type=int)
        mois = request.form.get("mois", type=int)
        annee = request.form.get("annee", type=int)
        montant = request.form.get("montant", type=float)

        employe = User.query.get(personnel_id) if personnel_id else None
        erreur = None
        if not employe or not mois or not annee or not montant or montant <= 0:
            erreur = "Merci de remplir tous les champs avec des valeurs valides."
        elif Salaire.query.filter_by(personnel_id=personnel_id, mois=mois, annee=annee).first():
            erreur = f"Un salaire existe déjà pour {employe.nom_complet} sur cette période."

        if erreur:
            flash(erreur, "error")
            return render_template("salaires/nouveau.html", personnel=personnel, mois_libelles=MOIS_LIBELLES)

        db.session.add(Salaire(
            personnel_id=personnel_id, mois=mois, annee=annee, montant=montant,
            responsable_id=current_user.id,
        ))
        db.session.commit()
        flash(f"Salaire de {employe.nom_complet} enregistré pour {MOIS_LIBELLES[mois-1]} {annee} — statut impayé.", "info")
        return redirect(url_for("salaires.liste"))

    return render_template("salaires/nouveau.html", personnel=personnel, mois_libelles=MOIS_LIBELLES)


@salaires_bp.route("/<int:salaire_id>/payer", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="salaires")
def marquer_paye(salaire_id):
    """Enregistre le versement — crée automatiquement la dépense
    correspondante dans la Caisse, même principe que les paiements de
    scolarité (Option A, sept. 2026) : jamais de ressaisie."""
    salaire = Salaire.query.get_or_404(salaire_id)
    if salaire.statut == "paye":
        flash("Ce salaire est déjà marqué comme payé.", "error")
        return redirect(url_for("salaires.liste"))

    salaire.statut = "paye"
    salaire.date_paiement = datetime.utcnow().date()
    db.session.flush()

    db.session.add(MouvementCaisse(
        date=salaire.date_paiement,
        type="Salaire",
        reference=f"SAL-{salaire.id}",
        libelle=f"Salaire — {salaire.personnel.nom_complet} ({salaire.libelle_periode})",
        recette=0,
        depense=salaire.montant,
        responsable_id=current_user.id,
        origine_module="salaires",
        origine_id=salaire.id,
        automatique=True,
    ))
    db.session.commit()
    flash(f"Salaire de {salaire.personnel.nom_complet} marqué payé — dépense enregistrée en Caisse.", "info")
    return redirect(url_for("salaires.liste"))


@salaires_bp.route("/<int:salaire_id>/supprimer", methods=["POST"])
@login_required
@roles_required(*ROLES_SUPPRESSION)
def supprimer(salaire_id):
    salaire = Salaire.query.get_or_404(salaire_id)
    MouvementCaisse.query.filter_by(origine_module="salaires", origine_id=salaire.id).delete()
    db.session.delete(salaire)
    db.session.commit()
    flash("Ligne de salaire supprimée (et sa dépense de Caisse associée si elle existait).", "info")
    return redirect(url_for("salaires.liste"))
