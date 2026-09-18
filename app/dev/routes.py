from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models.user import User, ROLES, STATUTS
from app.models.permission import Permission, MODULES
from app.services.permissions import toutes_les_permissions, vider_cache
from app.services.modules_par_defaut import ROLES_PAR_DEFAUT
from app.services.journal import journaliser
from app.dev import dev_bp
from app.utils import roles_required


@dev_bp.route("/")
@login_required
@roles_required("developpeur", module="gestion_roles")
def utilisateurs():
    """Attribution des rôles et statuts — accessible au développeur et au
    fondateur (décision du fondateur, sept. 2026). Le secrétariat ne peut
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
@roles_required("developpeur", module="gestion_roles")
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

    if utilisateur.id == current_user.id and nouveau_role != current_user.role:
        flash("Tu ne peux pas changer ton propre rôle depuis cet écran — demande à un autre développeur ou fondateur de le faire.", "error")
        return redirect(url_for("dev.utilisateurs"))

    ancien_role, ancien_statut = utilisateur.role, utilisateur.statut
    utilisateur.role = nouveau_role
    utilisateur.statut = nouveau_statut
    journaliser(
        "modification_role_statut",
        details=f"{utilisateur.nom_complet} : {ancien_role}/{ancien_statut} → {nouveau_role}/{nouveau_statut}",
        cible_type="User", cible_id=utilisateur.id,
    )
    db.session.commit()

    flash(f"{utilisateur.nom_complet} : rôle « {nouveau_role} », statut « {nouveau_statut} ».", "info")
    return redirect(url_for("dev.utilisateurs"))


@dev_bp.route("/utilisateur/<int:user_id>/supprimer", methods=["POST"])
@login_required
@roles_required("developpeur")
def supprimer_utilisateur(user_id):
    """Suppression réelle d'un compte — jamais un simple changement de
    statut. On nettoie d'abord tout ce qui pointe vers lui pour ne
    jamais laisser une donnée orpheline ni casser l'intégrité de la
    base (sept. 2026)."""
    from app.models.eleve import Eleve
    from app.models.enseignant import Enseignant
    from app.models.paiement import Paiement
    from app.models.mouvement_caisse import MouvementCaisse
    from app.models.salaire import Salaire
    from app.models.annonce import Annonce
    from app.models.test_niveau import TestNiveau

    utilisateur = User.query.get_or_404(user_id)

    if utilisateur.id == current_user.id:
        flash("Tu ne peux pas supprimer ton propre compte depuis cet écran.", "error")
        return redirect(url_for("dev.utilisateurs"))

    # On bloque si des salaires existent pour cette personne — les
    # supprimer silencieusement effacerait un historique de paiement
    # réel. Il faut d'abord les traiter (ex. les réaffecter) à la main.
    if Salaire.query.filter_by(personnel_id=utilisateur.id).count() > 0:
        flash(
            f"Impossible de supprimer {utilisateur.nom_complet} : des salaires lui sont "
            f"rattachés dans l'historique. Traite-les d'abord dans le module Salaires.",
            "error",
        )
        return redirect(url_for("dev.utilisateurs"))

    # L'association élève-parents (table de liaison) est nettoyée
    # automatiquement par SQLAlchemy à la suppression.

    eleve_lie = Eleve.query.filter_by(user_id=utilisateur.id).first()
    if eleve_lie:
        eleve_lie.user_id = None

    profil_enseignant = Enseignant.query.filter_by(user_id=utilisateur.id).first()
    if profil_enseignant:
        db.session.delete(profil_enseignant)  # supprime aussi ses affectations (cascade)

    Paiement.query.filter_by(enregistre_par_id=utilisateur.id).update({"enregistre_par_id": None})
    MouvementCaisse.query.filter_by(responsable_id=utilisateur.id).update({"responsable_id": None})
    Salaire.query.filter_by(responsable_id=utilisateur.id).update({"responsable_id": None})
    Annonce.query.filter_by(auteur_id=utilisateur.id).update({"auteur_id": None})
    TestNiveau.query.filter_by(evaluateur_id=utilisateur.id).update({"evaluateur_id": None})

    nom = utilisateur.nom_complet
    role_supprime = utilisateur.role
    journaliser(
        "suppression_utilisateur",
        details=f"{nom} ({role_supprime}, {utilisateur.email})",
        cible_type="User", cible_id=utilisateur.id,
    )
    db.session.delete(utilisateur)
    db.session.commit()

    flash(f"Compte de {nom} supprimé définitivement.", "info")
    return redirect(url_for("dev.utilisateurs"))


ROLES_MATRICE = [r for r in ROLES if r != "developpeur"]  # accès complet, inutile à afficher/modifier


@dev_bp.route("/journal")
@login_required
@roles_required("developpeur", module="journal_actions")
def journal():
    from app.models.journal import JournalAction

    utilisateur_id = request.args.get("utilisateur_id", type=int)
    action = request.args.get("action", "").strip()

    requete = JournalAction.query
    if utilisateur_id:
        requete = requete.filter_by(utilisateur_id=utilisateur_id)
    if action:
        requete = requete.filter(JournalAction.action == action)

    entrees = requete.order_by(JournalAction.date_action.desc()).limit(500).all()
    actions_disponibles = sorted({a for (a,) in db.session.query(JournalAction.action).distinct()})
    utilisateurs_disponibles = User.query.order_by(User.nom_complet).all()

    return render_template(
        "dev/journal.html", entrees=entrees, actions_disponibles=actions_disponibles,
        utilisateurs_disponibles=utilisateurs_disponibles,
        filtre_utilisateur_id=utilisateur_id, filtre_action=action,
    )


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

    journaliser("modification_permissions", details="Matrice de permissions mise à jour")
    db.session.commit()
    vider_cache()
    flash("Permissions mises à jour.", "info")
    return redirect(url_for("dev.permissions"))
