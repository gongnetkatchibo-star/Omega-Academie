from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from sqlalchemy import func

from app.extensions import db
from app.models.message import Message
from app.models.user import User
from app.messagerie import messagerie_bp
from app.utils import roles_required

ROLES_GESTION = ["secretaire", "directeur_primaire", "directeur_college", "fondateur", "administrateur_general"]


def _gere_la_messagerie():
    from app.services.permissions import role_a_acces
    return role_a_acces(current_user.role, "messagerie", ROLES_GESTION)


def _est_famille(utilisateur):
    """Un parent, ou tout compte auquel un enfant est rattaché (un
    enseignant ou un comptable peut aussi être parent d'élève)."""
    return utilisateur.role == "parent" or bool(utilisateur.enfants)


def non_lus_pour(utilisateur):
    """Messages en attente de lecture, pour le compteur du menu."""
    if utilisateur.role == "developpeur":
        return 0
    total = 0
    if _est_famille(utilisateur):
        total += Message.query.filter_by(parent_id=utilisateur.id, lu_par_parent=False).count()
    if _gere_la_messagerie():
        total += Message.query.filter_by(lu_par_ecole=False).count()
    return total


def _prevenir_l_ecole(parent, contenu):
    """Email au secrétariat (à défaut, à la direction) : un parent a écrit."""
    from app.services.notifications import notifier

    destinataires = [u.email for u in User.query.filter(User.statut == "actif", User.role == "secretaire").all()
                     if u.email and not u.email.endswith(".local")]
    if not destinataires:
        destinataires = [u.email for u in User.query.filter(User.statut == "actif",
                                                             User.role.in_(("fondateur", "administrateur_general"))).all()
                         if u.email and not u.email.endswith(".local")]
    if destinataires:
        extrait = contenu if len(contenu) <= 500 else contenu[:500] + "…"
        notifier(destinataires, f"Nouveau message de {parent.nom_complet}",
                 f"{parent.nom_complet} a écrit à l'école :\n\n{extrait}\n\nRépondre : "
                 f"{url_for('messagerie.fil', parent_id=parent.id, _external=True)}")


def _prevenir_le_parent(parent, contenu):
    from app.services.notifications import notifier, signature

    if parent.email and not parent.email.endswith(".local"):
        extrait = contenu if len(contenu) <= 500 else contenu[:500] + "…"
        notifier([parent.email], "Réponse de l'école",
                 f"Bonjour {parent.nom_complet},\n\nL'école vous a répondu :\n\n{extrait}\n\n"
                 f"Lire la conversation : {url_for('messagerie.mon_fil', _external=True)}\n\n{signature()}")


@messagerie_bp.route("/")
@login_required
def index():
    if _gere_la_messagerie():
        # Une seule requête : nombre de non lus et date du dernier message par parent.
        resume = db.session.query(
            Message.parent_id,
            func.sum(db.case((Message.lu_par_ecole.is_(False), 1), else_=0)),
            func.max(Message.date_envoi),
        ).group_by(Message.parent_id).all()
        parents = {p.id: p for p in User.query.filter(User.id.in_([r[0] for r in resume] or [0])).all()}
        fils = sorted(
            ({"parent": parents[pid], "non_lus": int(nb or 0), "dernier": dernier} for pid, nb, dernier in resume if pid in parents),
            key=lambda f: (f["non_lus"] == 0, -(f["dernier"].timestamp() if f["dernier"] else 0)),
        )
        return render_template("messagerie/liste_fils.html", fils=fils, est_famille=_est_famille(current_user))
    if _est_famille(current_user):
        return redirect(url_for("messagerie.mon_fil"))
    abort(403)


@messagerie_bp.route("/mon-fil")
@login_required
def mon_fil():
    if not _est_famille(current_user):
        abort(403)
    messages = Message.query.filter_by(parent_id=current_user.id).order_by(Message.date_envoi).all()
    Message.query.filter_by(parent_id=current_user.id, lu_par_parent=False).update({"lu_par_parent": True})
    db.session.commit()
    return render_template("messagerie/fil_parent.html", messages=messages)


@messagerie_bp.route("/envoyer", methods=["POST"])
@login_required
def envoyer():
    """Une famille écrit dans son propre fil — jamais dans celui d'un
    autre (sept. 2026)."""
    if not _est_famille(current_user):
        abort(403)

    contenu = request.form.get("contenu", "").strip()
    if not contenu:
        flash("Le message ne peut pas être vide.", "error")
        return redirect(url_for("messagerie.mon_fil"))
    if len(contenu) > 3000:
        flash("Message trop long (3 000 caractères au plus).", "error")
        return redirect(url_for("messagerie.mon_fil"))

    db.session.add(Message(parent_id=current_user.id, auteur_id=current_user.id, contenu=contenu, lu_par_ecole=False, lu_par_parent=True))
    db.session.commit()
    _prevenir_l_ecole(current_user, contenu)
    flash("Message envoyé à l'école.", "info")
    return redirect(url_for("messagerie.mon_fil"))


def _parent_ou_404(parent_id):
    parent = db.get_or_404(User, parent_id)
    if not _est_famille(parent):
        abort(404)
    return parent


@messagerie_bp.route("/<int:parent_id>")
@login_required
@roles_required(*ROLES_GESTION, module="messagerie")
def fil(parent_id):
    parent = _parent_ou_404(parent_id)
    messages = Message.query.filter_by(parent_id=parent_id).order_by(Message.date_envoi).all()
    Message.query.filter_by(parent_id=parent_id, lu_par_ecole=False).update({"lu_par_ecole": True})
    db.session.commit()
    return render_template("messagerie/fil_ecole.html", parent=parent, messages=messages)


@messagerie_bp.route("/<int:parent_id>/repondre", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module="messagerie")
def repondre(parent_id):
    parent = _parent_ou_404(parent_id)
    contenu = request.form.get("contenu", "").strip()
    if not contenu or len(contenu) > 3000:
        flash("Écris une réponse (3 000 caractères au plus).", "error")
        return redirect(url_for("messagerie.fil", parent_id=parent_id))

    db.session.add(Message(parent_id=parent_id, auteur_id=current_user.id, contenu=contenu, lu_par_ecole=True, lu_par_parent=False))
    db.session.commit()
    _prevenir_le_parent(parent, contenu)
    flash("Réponse envoyée.", "info")
    return redirect(url_for("messagerie.fil", parent_id=parent_id))
