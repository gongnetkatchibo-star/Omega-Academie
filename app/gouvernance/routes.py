"""Côté école : abonnement, factures, espace de stockage et assistance
de la plateforme — pour le fondateur et l'administrateur général."""

from flask import render_template, redirect, url_for, flash, request, abort, make_response, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.gouvernance import gouvernance_bp
from app.models.gouvernance import DemandeSupport, Facture, CATEGORIES_DEMANDE, STATUTS_DEMANDE
from app.services.journal import journaliser
from app.services.tenant import ecole_courante, ecole_courante_id
from app.utils import roles_required

ROLES_DIRECTION = ("fondateur", "administrateur_general")


@gouvernance_bp.route("/abonnement")
@login_required
@roles_required(*ROLES_DIRECTION)
def abonnement():
    from app.services import abonnements, stockage

    ecole = ecole_courante() or abort(404)
    return render_template(
        "gouvernance/abonnement.html", etab=ecole, etat=abonnements.etat(ecole), factures=abonnements.factures_de(ecole.id),
        stockage=stockage.etat(ecole), eleves_actifs=abonnements.nombre_eleves_actifs(ecole.id),
    )


@gouvernance_bp.route("/facture/<int:facture_id>/pdf")
@login_required
@roles_required(*ROLES_DIRECTION)
def facture_pdf(facture_id):
    from app.services.abonnements import facture_pdf as construire

    facture = db.session.get(Facture, facture_id)
    if facture is None or facture.ecole_id != ecole_courante_id():
        abort(404)
    reponse = make_response(construire(facture, current_app.config.get("PLATEFORME_NOM", "Toumaï Edu School"),
                                       current_app.config.get("PLATEFORME_EMAIL_SUPPORT")))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = f"attachment; filename=facture_{facture.numero}.pdf"
    return reponse


@gouvernance_bp.route("/assistance", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_DIRECTION)
def assistance():
    """Écrire à l'administration de la plateforme et suivre ses réponses."""
    from app.services.assistance import ajouter_message, notifier

    ecole_id = ecole_courante_id() or abort(404)
    if request.method == "POST":
        sujet = request.form.get("sujet", "").strip()
        contenu = request.form.get("contenu", "").strip()
        categorie = request.form.get("categorie") if request.form.get("categorie") in CATEGORIES_DEMANDE else "question"
        if not sujet or not contenu:
            flash("Merci d'indiquer un sujet et ton message.", "error")
        elif len(sujet) > 150 or len(contenu) > 5000:
            flash("Sujet : 150 caractères au plus ; message : 5 000 caractères au plus.", "error")
        else:
            demande = DemandeSupport(ecole_id=ecole_id, auteur_id=current_user.id, sujet=sujet, categorie=categorie)
            db.session.add(demande)
            ajouter_message(demande, current_user, contenu, de_la_plateforme=False)
            journaliser("demande_assistance", details=sujet)
            db.session.commit()
            notifier(demande, False, contenu)
            flash("Demande envoyée à l'administration de la plateforme. Tu seras prévenu par email de la réponse.", "info")
            return redirect(url_for("gouvernance.demande", demande_id=demande.id))
    demandes = DemandeSupport.query.filter_by(ecole_id=ecole_id).order_by(DemandeSupport.date_maj.desc()).all()
    return render_template("gouvernance/assistance.html", demandes=demandes, categories=CATEGORIES_DEMANDE, form=request.form)


@gouvernance_bp.route("/assistance/<int:demande_id>", methods=["GET", "POST"])
@login_required
@roles_required(*ROLES_DIRECTION)
def demande(demande_id):
    from app.services.assistance import ajouter_message, notifier

    demande = db.session.get(DemandeSupport, demande_id)
    if demande is None or demande.ecole_id != ecole_courante_id():
        abort(404)
    if request.method == "POST":
        contenu = request.form.get("contenu", "").strip()
        if not contenu or len(contenu) > 5000:
            flash("Écris ton message (5 000 caractères au plus).", "error")
        else:
            ajouter_message(demande, current_user, contenu, de_la_plateforme=False)
            db.session.commit()
            notifier(demande, False, contenu)
            flash("Message envoyé.", "info")
        return redirect(url_for("gouvernance.demande", demande_id=demande.id))
    if demande.non_lu_ecole:
        demande.non_lu_ecole = False
        db.session.commit()
    return render_template("gouvernance/demande.html", demande=demande, statuts=STATUTS_DEMANDE, cote_plateforme=False)
