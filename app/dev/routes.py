from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models.user import User, ROLES, STATUTS
from app.models.permission import Permission, MODULES
from app.services.permissions import toutes_les_permissions, vider_cache
from app.services.modules_par_defaut import ROLES_PAR_DEFAUT
from app.dev import dev_bp
from app.utils import roles_required


@dev_bp.route("/")
@login_required
@roles_required("developpeur")
def utilisateurs():
    """Espace développeur : seule zone de l'application qui peut changer
    le rôle ou le statut de n'importe quel compte. Le secrétariat ne peut
    qu'approuver/refuser (statut) les comptes en attente ; il ne peut pas
    changer un rôle une fois le compte créé."""
    q = request.args.get("q", "").strip()
    requete = User.query
    if q:
        requete = requete.filter(
            db.or_(User.nom_complet.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"))
        )
    utilisateurs = requete.order_by(User.date_creation.desc()).all()
    return render_template(
        "dev/utilisateurs.html", utilisateurs=utilisateurs, roles=ROLES, statuts=STATUTS, q=q
    )


@dev_bp.route("/utilisateur/<int:user_id>", methods=["POST"])
@login_required
@roles_required("developpeur")
def modifier_utilisateur(user_id):
    utilisateur = User.query.get_or_404(user_id)

    nouveau_role = request.form.get("role")
    nouveau_statut = request.form.get("statut")

    if nouveau_role not in ROLES:
        flash("Rôle invalide.", "error")
        return redirect(url_for("dev.utilisateurs"))

    if nouveau_statut not in STATUTS:
        flash("Statut invalide.", "error")
        return redirect(url_for("dev.utilisateurs"))

    if utilisateur.id == current_user.id and nouveau_role != "developpeur":
        flash("Tu ne peux pas retirer ton propre rôle développeur depuis cet écran.", "error")
        return redirect(url_for("dev.utilisateurs"))

    utilisateur.role = nouveau_role
    utilisateur.statut = nouveau_statut
    db.session.commit()

    flash(f"{utilisateur.nom_complet} : rôle « {nouveau_role} », statut « {nouveau_statut} ».", "info")
    return redirect(url_for("dev.utilisateurs"))


ROLES_MATRICE = [r for r in ROLES if r != "developpeur"]  # accès complet, inutile à afficher/modifier


@dev_bp.route("/permissions")
@login_required
@roles_required("developpeur")
def permissions():
    modules_cles = [cle for cle, _ in MODULES]
    etat = toutes_les_permissions(ROLES_MATRICE, modules_cles)
    return render_template(
        "dev/permissions.html", roles=ROLES_MATRICE, modules=MODULES, etat=etat,
        roles_par_defaut=ROLES_PAR_DEFAUT,
    )


@dev_bp.route("/permissions/enregistrer", methods=["POST"])
@login_required
@roles_required("developpeur")
def enregistrer_permissions():
    """Une case cochée = accès autorisé pour ce rôle sur ce module ; une
    case décochée envoyée = accès explicitement refusé. On enregistre une
    ligne Permission pour CHAQUE couple (rôle, module) affiché — qu'elle
    confirme ou inverse la valeur par défaut — pour que l'écran affiche
    toujours l'état réel, sans ambiguïté."""
    modules_cles = [cle for cle, _ in MODULES]

    for role in ROLES_MATRICE:
        for module in modules_cles:
            case = f"{role}__{module}"
            autorise = request.form.get(case) == "on"

            ligne = Permission.query.filter_by(role=role, module=module).first()
            if ligne:
                ligne.autorise = autorise
            else:
                db.session.add(Permission(role=role, module=module, autorise=autorise))

    db.session.commit()
    vider_cache()
    flash("Permissions mises à jour.", "info")
    return redirect(url_for("dev.permissions"))
