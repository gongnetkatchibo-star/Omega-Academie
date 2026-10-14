from flask import render_template, redirect, url_for, flash
from flask_login import login_required

from app.extensions import db
from app.models.user import User
from app.secretariat import secretariat_bp
from app.utils import roles_required

ROLES_VALIDATION = ["secretaire", "fondateur", "administrateur_general"]


@secretariat_bp.route("/demandes")
@login_required
@roles_required(*ROLES_VALIDATION, module="secretariat")
def demandes():
    en_attente = User.query.filter_by(statut="en_attente").order_by(User.date_creation.asc()).all()
    return render_template("secretariat/demandes.html", demandes=en_attente)


@secretariat_bp.route("/demandes/<int:user_id>/approuver", methods=["POST"])
@login_required
@roles_required(*ROLES_VALIDATION, module="secretariat")
def approuver(user_id):
    user = db.get_or_404(User, user_id)
    if user.statut != "en_attente":
        # Un compte verrouillé ou refusé ne se rouvre pas d'ici.
        flash(f"Le compte de {user.nom_complet} n'est pas en attente de validation.", "error")
        return redirect(url_for("secretariat.demandes"))
    user.statut = "actif"
    from app.services.journal import journaliser
    journaliser("approbation_compte", details=f"{user.nom_complet} ({user.role})", cible_type="User", cible_id=user.id)
    db.session.commit()
    flash(f"Compte de {user.nom_complet} approuvé.", "info")
    return redirect(url_for("secretariat.demandes"))


@secretariat_bp.route("/demandes/<int:user_id>/refuser", methods=["POST"])
@login_required
@roles_required(*ROLES_VALIDATION, module="secretariat")
def refuser(user_id):
    user = db.get_or_404(User, user_id)
    if user.statut != "en_attente":
        flash(f"Le compte de {user.nom_complet} n'est pas en attente de validation.", "error")
        return redirect(url_for("secretariat.demandes"))
    user.statut = "refuse"
    if user.role == "eleve":
        # Le dossier de l'élève est libéré : le vrai titulaire du matricule
        # peut créer son compte (sinon un camarade qui a pris son matricule
        # le bloquait pour de bon, audit oct. 2026).
        from app.models.eleve import Eleve
        Eleve.query.filter_by(user_id=user.id).update({"user_id": None})
    from app.services.journal import journaliser
    journaliser("refus_compte", details=f"{user.nom_complet} ({user.role})", cible_type="User", cible_id=user.id)
    db.session.commit()
    flash(f"Demande de {user.nom_complet} refusée.", "info")
    return redirect(url_for("secretariat.demandes"))
