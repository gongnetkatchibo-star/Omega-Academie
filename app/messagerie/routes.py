from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.message import Message
from app.models.user import User
from app.messagerie import messagerie_bp
from app.utils import roles_required

ROLES_GESTION = ["secretaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general"]


@messagerie_bp.route("/")
@login_required
def index():
    if current_user.role == "parent":
        messages = Message.query.filter_by(parent_id=current_user.id).order_by(Message.date_envoi).all()
        Message.query.filter_by(parent_id=current_user.id, lu_par_parent=False).update({"lu_par_parent": True})
        db.session.commit()
        return render_template("messagerie/fil_parent.html", messages=messages)

    if current_user.role in ROLES_GESTION or current_user.role == "developpeur":
        parents_avec_messages = (
            db.session.query(User)
            .join(Message, Message.parent_id == User.id)
            .distinct()
            .all()
        )
        non_lus = {
            p.id: Message.query.filter_by(parent_id=p.id, lu_par_ecole=False).count()
            for p in parents_avec_messages
        }
        parents_avec_messages.sort(key=lambda p: non_lus.get(p.id, 0), reverse=True)
        return render_template("messagerie/liste_fils.html", parents=parents_avec_messages, non_lus=non_lus)

    abort(403)


@messagerie_bp.route("/envoyer", methods=["POST"])
@login_required
def envoyer():
    """Un parent écrit dans son propre fil — jamais dans celui d'un
    autre (sept. 2026)."""
    if current_user.role != "parent":
        abort(403)

    contenu = request.form.get("contenu", "").strip()
    if not contenu:
        flash("Le message ne peut pas être vide.", "error")
        return redirect(url_for("messagerie.index"))

    db.session.add(Message(parent_id=current_user.id, auteur_id=current_user.id, contenu=contenu, lu_par_ecole=False, lu_par_parent=True))
    db.session.commit()
    flash("Message envoyé à l'école.", "info")
    return redirect(url_for("messagerie.index"))


@messagerie_bp.route("/<int:parent_id>")
@login_required
@roles_required(*ROLES_GESTION, module="messagerie")
def fil(parent_id):
    parent = User.query.get_or_404(parent_id)
    messages = Message.query.filter_by(parent_id=parent_id).order_by(Message.date_envoi).all()
    Message.query.filter_by(parent_id=parent_id, lu_par_ecole=False).update({"lu_par_ecole": True})
    db.session.commit()
    return render_template("messagerie/fil_ecole.html", parent=parent, messages=messages)


@messagerie_bp.route("/<int:parent_id>/repondre", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="messagerie")
def repondre(parent_id):
    parent = User.query.get_or_404(parent_id)
    contenu = request.form.get("contenu", "").strip()
    if not contenu:
        flash("Le message ne peut pas être vide.", "error")
        return redirect(url_for("messagerie.fil", parent_id=parent_id))

    db.session.add(Message(parent_id=parent_id, auteur_id=current_user.id, contenu=contenu, lu_par_ecole=True, lu_par_parent=False))
    db.session.commit()
    flash("Réponse envoyée.", "info")
    return redirect(url_for("messagerie.fil", parent_id=parent_id))
