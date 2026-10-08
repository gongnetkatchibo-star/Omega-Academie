"""Prêt de livres papier : catalogue de la bibliothèque, prêts aux élèves
et au personnel, retours et retards."""

from datetime import timedelta

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.prets import prets_bp
from app.models.eleve import Eleve
from app.models.livre import Livre, Pret
from app.models.user import User
from app.services.pagination import paginer
from app.services.suivi_eleve import DIRECTION, date_du_formulaire
from app.services.temps import aujourd_hui
from app.utils import roles_required

ROLES_GESTION = ["bibliothecaire"] + DIRECTION
MODULE = "prets"
DUREE_PRET_JOURS = 14


@prets_bp.route("/")
@login_required
@roles_required(*ROLES_GESTION, module=MODULE)
def catalogue():
    terme = request.args.get("q", "").strip()
    requete = Livre.query.options(db.selectinload(Livre.prets))
    if terme:
        motif = f"%{terme}%"
        requete = requete.filter(db.or_(Livre.titre.ilike(motif), Livre.auteur.ilike(motif), Livre.cote.ilike(motif)))
    page = paginer(requete.order_by(Livre.titre))
    return render_template("prets/catalogue.html", page=page, terme=terme)


def _lire_livre(livre):
    titre = request.form.get("titre", "").strip()
    if not titre:
        return "Le titre est obligatoire."
    exemplaires = request.form.get("exemplaires", type=int) or 1
    if not 1 <= exemplaires <= 999:
        return "Nombre d'exemplaires invalide."
    if livre.id and exemplaires < len(livre.prets_en_cours):
        return "Il y a plus d'exemplaires prêtés que ce nombre."
    livre.titre = titre[:200]
    livre.auteur = request.form.get("auteur", "").strip()[:150] or None
    livre.cote = request.form.get("cote", "").strip()[:40] or None
    livre.categorie = request.form.get("categorie", "").strip()[:80] or None
    livre.exemplaires = exemplaires
    return None


@prets_bp.route("/nouveau", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module=MODULE)
def nouveau():
    livre = Livre()
    erreur = _lire_livre(livre)
    if erreur:
        flash(erreur, "error")
        return redirect(url_for("prets.catalogue"))
    db.session.add(livre)
    db.session.commit()
    flash("Livre ajouté au catalogue.", "info")
    return redirect(url_for("prets.livre", livre_id=livre.id))


@prets_bp.route("/<int:livre_id>", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_GESTION, module=MODULE)
def livre(livre_id):
    livre_obj = db.get_or_404(Livre, livre_id)
    if request.method == "POST":
        erreur = _lire_livre(livre_obj)
        if erreur:
            db.session.rollback()
            flash(erreur, "error")
        else:
            db.session.commit()
            flash("Livre mis à jour.", "info")
        return redirect(url_for("prets.livre", livre_id=livre_obj.id))
    eleves = Eleve.query.options(db.joinedload(Eleve.classe)).filter_by(actif=True).order_by(Eleve.nom_complet).all()
    personnel = (
        User.query.filter(User.statut == "actif", User.role.notin_(["eleve", "parent"]))
        .order_by(User.nom_complet).all()
    )
    jour = aujourd_hui()
    return render_template(
        "prets/livre.html", livre=livre_obj, eleves=eleves, personnel=personnel,
        aujourd_hui=jour, retour_prevu=jour + timedelta(days=DUREE_PRET_JOURS),
    )


@prets_bp.route("/<int:livre_id>/supprimer", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module=MODULE)
def supprimer(livre_id):
    livre_obj = db.get_or_404(Livre, livre_id)
    if livre_obj.prets_en_cours:
        flash("Ce livre a encore des exemplaires prêtés.", "error")
        return redirect(url_for("prets.livre", livre_id=livre_obj.id))
    for pret in list(livre_obj.prets):
        db.session.delete(pret)
    db.session.delete(livre_obj)
    db.session.commit()
    flash("Livre retiré du catalogue.", "info")
    return redirect(url_for("prets.catalogue"))


@prets_bp.route("/<int:livre_id>/preter", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module=MODULE)
def preter(livre_id):
    livre_obj = db.get_or_404(Livre, livre_id)
    emprunteur = request.form.get("emprunteur", "")
    eleve = user = None
    if emprunteur.startswith("e"):
        eleve = Eleve.query.filter_by(id=_entier(emprunteur[1:]), actif=True).first()
    elif emprunteur.startswith("u"):
        user = User.query.filter(User.id == _entier(emprunteur[1:]), User.statut == "actif",
                                 User.role.notin_(["eleve", "parent"])).first()
    if eleve is None and user is None:
        flash("Choisis la personne qui emprunte le livre.", "error")
    elif livre_obj.disponibles < 1:
        flash("Aucun exemplaire disponible.", "error")
    else:
        date_pret = date_du_formulaire("date_pret")
        retour = date_du_formulaire("date_retour_prevue", facultative=True) or date_pret + timedelta(days=DUREE_PRET_JOURS)
        if retour < date_pret:
            flash("La date de retour ne peut pas précéder la date du prêt.", "error")
        else:
            db.session.add(Pret(
                livre_id=livre_obj.id, eleve_id=eleve.id if eleve else None, user_id=user.id if user else None,
                date_pret=date_pret, date_retour_prevue=retour, prete_par_id=current_user.id,
                remarque=request.form.get("remarque", "").strip()[:200] or None,
            ))
            db.session.commit()
            flash("Prêt enregistré.", "info")
    return redirect(url_for("prets.livre", livre_id=livre_obj.id))


def _entier(texte):
    try:
        return int(texte)
    except ValueError:
        return 0


@prets_bp.route("/pret/<int:pret_id>/retour", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module=MODULE)
def retour(pret_id):
    pret = db.get_or_404(Pret, pret_id)
    if pret.date_retour is None:
        pret.date_retour = aujourd_hui()
        db.session.commit()
        flash("Retour enregistré.", "info")
    if request.form.get("retour") == "prets":
        return redirect(url_for("prets.prets"))
    return redirect(url_for("prets.livre", livre_id=pret.livre_id))


@prets_bp.route("/prets")
@login_required
@roles_required(*ROLES_GESTION, module=MODULE)
def prets():
    """Livres actuellement prêtés ; les retards en premier."""
    requete = Pret.query.options(db.joinedload(Pret.livre), db.joinedload(Pret.eleve), db.joinedload(Pret.emprunteur_personnel)) \
        .filter(Pret.date_retour.is_(None))
    if request.args.get("retard"):
        requete = requete.filter(Pret.date_retour_prevue < aujourd_hui())
    page = paginer(requete.order_by(Pret.date_retour_prevue))
    return render_template("prets/prets.html", page=page, retard=bool(request.args.get("retard")))


@prets_bp.route("/pret/<int:pret_id>/relancer", methods=["POST"])
@login_required
@roles_required(*ROLES_GESTION, module=MODULE)
def relancer(pret_id):
    """Email de rappel aux parents (élève) ou à l'emprunteur (personnel)."""
    from app.services.notifications import notifier, signature

    pret = db.get_or_404(Pret, pret_id)
    if pret.date_retour is not None:
        return redirect(url_for("prets.prets"))
    if pret.eleve:
        destinataires = [p.email for p in pret.eleve.parents if p.email]
        sujet = f"Livre à rendre — {pret.eleve.nom_complet}"
        texte = f"{pret.eleve.nom_complet} a emprunté « {pret.livre.titre} »"
    else:
        destinataires = [pret.emprunteur_personnel.email] if pret.emprunteur_personnel else []
        sujet = "Livre à rendre à la bibliothèque"
        texte = f"Vous avez emprunté « {pret.livre.titre} »"
    texte += f", à rendre le {pret.date_retour_prevue.strftime('%d/%m/%Y')}. Merci de le rapporter à la bibliothèque."
    if destinataires and notifier(destinataires, sujet, f"Bonjour,\n\n{texte}\n\n{signature()}"):
        flash("Rappel envoyé.", "info")
    else:
        flash("Aucune adresse email pour ce rappel, ou l'envoi a échoué.", "error")
    return redirect(url_for("prets.prets"))
