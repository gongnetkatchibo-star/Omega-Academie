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
    user = User.query.get_or_404(user_id)
    user.statut = "actif"
    db.session.commit()
    flash(f"Compte de {user.nom_complet} approuvé.", "info")
    return redirect(url_for("secretariat.demandes"))


@secretariat_bp.route("/demandes/<int:user_id>/refuser", methods=["POST"])
@login_required
@roles_required(*ROLES_VALIDATION, module="secretariat")
def refuser(user_id):
    user = User.query.get_or_404(user_id)
    user.statut = "refuse"
    db.session.commit()
    flash(f"Demande de {user.nom_complet} refusée.", "info")
    return redirect(url_for("secretariat.demandes"))
