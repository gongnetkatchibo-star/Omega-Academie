"""Console de la plateforme : abonnements et factures, stockage,
assistance, annonces de la plateforme, journal de toutes les écoles,
sauvegarde d'une école sans y entrer (oct. 2026)."""

from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, abort, make_response, current_app, g, send_file
from flask_login import login_required, current_user
from sqlalchemy import select

from app.extensions import db
from app.utils import piece_jointe
from app.models.ecole import Ecole
from app.models.gouvernance import (
    AnnoncePlateforme, DemandeSupport, Facture, MODES_FACTURATION, PERIODICITES, MODES_REGLEMENT, STATUTS_DEMANDE,
)
from app.plateforme import plateforme_bp
from app.plateforme.routes import super_admin_requis, _journaliser

TOUS = {"tous_etablissements": True}


def _ecole(ecole_id):
    return db.session.get(Ecole, ecole_id) or abort(404)


@plateforme_bp.route("/<int:ecole_id>/abonnement", methods=["GET", "POST"])
@login_required
@super_admin_requis
def abonnement(ecole_id):
    """Formule, tarif, rythme, échéance, quota de stockage et contact."""
    from app.services import abonnements, stockage
    from app.utils import montant_positif_ou_nul

    ecole = _ecole(ecole_id)
    if request.method == "POST":
        erreurs = []
        mode = request.form.get("mode_facturation") or None
        if mode and mode not in MODES_FACTURATION:
            erreurs.append("Mode de facturation inconnu.")
        tarif = montant_positif_ou_nul(request.form.get("tarif", "").strip())
        if tarif is None:
            erreurs.append("Le tarif doit être un montant entier en FCFA.")
        periodicite = request.form.get("periodicite")
        if periodicite not in PERIODICITES:
            erreurs.append("Rythme de facturation inconnu.")
        echeance = None
        if request.form.get("date_echeance"):
            try:
                echeance = datetime.strptime(request.form["date_echeance"], "%Y-%m-%d").date()
            except ValueError:
                erreurs.append("Date de début de la prochaine période invalide.")
        try:
            quota_go = float(request.form.get("quota_go", "5").replace(",", "."))
            if not 0.1 <= quota_go <= 1000:
                raise ValueError
        except ValueError:
            erreurs.append("Le quota de stockage doit être compris entre 0,1 et 1 000 Go.")
            quota_go = None
        if erreurs:
            for e in erreurs:
                flash(e, "error")
        else:
            ecole.mode_facturation, ecole.tarif, ecole.periodicite = mode, tarif or None, periodicite
            ecole.nom_formule = request.form.get("nom_formule", "").strip()[:60] or None
            ecole.date_echeance = echeance
            ecole.quota_stockage = int(quota_go * 1024 ** 3)
            for champ, longueur in (("contact_nom", 120), ("contact_telephone", 30), ("contact_email", 120)):
                setattr(ecole, champ, request.form.get(champ, "").strip()[:longueur] or None)
            ecole.notes_plateforme = request.form.get("notes_plateforme", "").strip()[:5000] or None
            _journaliser(ecole.id, "abonnement_modifie", f"{abonnements.libelle_formule(ecole)} ; quota {quota_go:g} Go")
            db.session.commit()
            flash("Abonnement, stockage et contact enregistrés.", "info")
            return redirect(url_for("plateforme.abonnement", ecole_id=ecole.id))
    return render_template(
        "plateforme/abonnement.html", etab=ecole, modes=MODES_FACTURATION, periodicites=PERIODICITES,
        etat=abonnements.etat(ecole), stockage=stockage.etat(ecole), factures=abonnements.factures_de(ecole.id),
        proposition=abonnements.proposition(ecole) if ecole.mode_facturation and ecole.tarif else None,
        modes_reglement=MODES_REGLEMENT, eleves_actifs=abonnements.nombre_eleves_actifs(ecole.id),
    )


@plateforme_bp.route("/<int:ecole_id>/factures/emettre", methods=["POST"])
@login_required
@super_admin_requis
def emettre_facture(ecole_id):
    from app.services import abonnements

    ecole = _ecole(ecole_id)
    if not (ecole.mode_facturation and ecole.tarif):
        flash("Règle d'abord la formule et le tarif de l'école.", "error")
        return redirect(url_for("plateforme.abonnement", ecole_id=ecole.id))
    quantite = request.form.get("quantite", type=int)
    facture = abonnements.emettre(ecole, quantite=quantite, note=request.form.get("note", "").strip())
    db.session.flush()
    _journaliser(ecole.id, "facture_emise", f"{facture.numero} — {facture.montant} FCFA")
    db.session.commit()
    envoyee = abonnements.notifier_facture(facture)
    flash(f"Facture {facture.numero} émise{' et envoyée par email à la direction' if envoyee else ''}.", "info")
    return redirect(url_for("plateforme.abonnement", ecole_id=ecole.id))


@plateforme_bp.route("/facture/<int:facture_id>/payer", methods=["POST"])
@login_required
@super_admin_requis
def payer_facture(facture_id):
    facture = db.session.get(Facture, facture_id) or abort(404)
    if facture.statut != "emise":
        flash("Cette facture n'est pas à payer.", "error")
    else:
        try:
            date_paiement = datetime.strptime(request.form.get("date_paiement", ""), "%Y-%m-%d").date()
        except ValueError:
            date_paiement = None
        mode = request.form.get("mode_reglement")
        if not date_paiement or mode not in MODES_REGLEMENT:
            flash("Indique la date et le mode du règlement.", "error")
        else:
            facture.statut, facture.date_paiement, facture.mode_reglement = "payee", date_paiement, mode
            facture.reference_reglement = request.form.get("reference_reglement", "").strip()[:80] or None
            _journaliser(facture.ecole_id, "facture_payee", f"{facture.numero} — {MODES_REGLEMENT[mode]}")
            db.session.commit()
            flash(f"Facture {facture.numero} marquée payée.", "info")
    return redirect(request.form.get("retour") or url_for("plateforme.abonnement", ecole_id=facture.ecole_id))


@plateforme_bp.route("/facture/<int:facture_id>/annuler", methods=["POST"])
@login_required
@super_admin_requis
def annuler_facture(facture_id):
    facture = db.session.get(Facture, facture_id) or abort(404)
    if facture.statut == "emise":
        facture.statut = "annulee"
        facture.note = (request.form.get("motif", "").strip() or facture.note or "")[:300] or None
        _journaliser(facture.ecole_id, "facture_annulee", facture.numero)
        db.session.commit()
        flash(f"Facture {facture.numero} annulée. L'échéance de l'école n'a pas changé : corrige-la si besoin.", "info")
    return redirect(url_for("plateforme.abonnement", ecole_id=facture.ecole_id))


@plateforme_bp.route("/facture/<int:facture_id>/pdf")
@login_required
@super_admin_requis
def facture_pdf(facture_id):
    from app.services.abonnements import facture_pdf as construire

    facture = db.session.get(Facture, facture_id) or abort(404)
    reponse = make_response(construire(facture, current_app.config.get("PLATEFORME_NOM", "Toumaï Edu School"),
                                       current_app.config.get("PLATEFORME_EMAIL_SUPPORT")))
    reponse.headers["Content-Type"] = "application/pdf"
    reponse.headers["Content-Disposition"] = piece_jointe(f"facture_{facture.numero}.pdf")
    return reponse


@plateforme_bp.route("/factures")
@login_required
@super_admin_requis
def factures():
    filtre = request.args.get("statut")
    requete = Facture.query
    if filtre in ("emise", "payee", "annulee"):
        requete = requete.filter_by(statut=filtre)
    from app.services.pagination import paginer
    page = paginer(requete.order_by(Facture.date_emission.desc(), Facture.id.desc()))
    impayees = Facture.query.filter_by(statut="emise").all()
    return render_template("plateforme/factures.html", factures=page, page=page, filtre=filtre,
                           total_du=sum(f.montant for f in impayees), nb_impayees=len(impayees),
                           modes_reglement=MODES_REGLEMENT)


# --------------------------------------------------------------- assistance
@plateforme_bp.route("/assistance")
@login_required
@super_admin_requis
def assistance():
    filtre = request.args.get("statut")
    requete = DemandeSupport.query
    if filtre in STATUTS_DEMANDE:
        requete = requete.filter_by(statut=filtre)
    else:
        requete = requete.filter(DemandeSupport.statut != "resolue")
    demandes = requete.order_by(DemandeSupport.non_lu_plateforme.desc(), DemandeSupport.date_maj.desc()).all()
    return render_template("plateforme/assistance.html", demandes=demandes, filtre=filtre, statuts=STATUTS_DEMANDE)


@plateforme_bp.route("/assistance/<int:demande_id>", methods=["GET", "POST"])
@login_required
@super_admin_requis
def demande(demande_id):
    from app.services.assistance import ajouter_message, notifier

    demande = db.session.get(DemandeSupport, demande_id) or abort(404)
    if request.method == "POST":
        contenu = request.form.get("contenu", "").strip()
        statut = request.form.get("statut")
        if contenu:
            if len(contenu) > 5000:
                flash("5 000 caractères au plus.", "error")
                return redirect(url_for("plateforme.demande", demande_id=demande.id))
            ajouter_message(demande, current_user, contenu, de_la_plateforme=True)
        if statut in STATUTS_DEMANDE:
            demande.statut = statut
        db.session.commit()
        if contenu:
            notifier(demande, True, contenu)
        flash("Réponse envoyée." if contenu else "Statut mis à jour.", "info")
        return redirect(url_for("plateforme.demande", demande_id=demande.id))
    if demande.non_lu_plateforme:
        demande.non_lu_plateforme = False
        db.session.commit()
    return render_template("gouvernance/demande.html", demande=demande, statuts=STATUTS_DEMANDE, cote_plateforme=True)


# ----------------------------------------------------- annonces de la plateforme
@plateforme_bp.route("/annonces", methods=["GET", "POST"])
@login_required
@super_admin_requis
def annonces():
    ecoles = db.session.query(Ecole).order_by(Ecole.nom).all()
    if request.method == "POST":
        titre = request.form.get("titre", "").strip()
        contenu = request.form.get("contenu", "").strip()
        ecole_id = request.form.get("ecole_id", type=int)
        public = request.form.get("public") if request.form.get("public") in ("direction", "tous") else "direction"
        date_fin = None
        if request.form.get("date_fin"):
            try:
                date_fin = datetime.strptime(request.form["date_fin"], "%Y-%m-%d").date()
            except ValueError:
                pass
        if not titre or not contenu or len(titre) > 150:
            flash("Titre (150 caractères au plus) et contenu obligatoires.", "error")
        elif ecole_id and not db.session.get(Ecole, ecole_id):
            flash("École inconnue.", "error")
        else:
            db.session.add(AnnoncePlateforme(titre=titre, contenu=contenu[:5000], ecole_id=ecole_id or None,
                                             public=public, date_fin=date_fin))
            db.session.commit()
            flash("Annonce publiée : elle s'affiche sur le tableau de bord des écoles concernées.", "info")
            return redirect(url_for("plateforme.annonces"))
    liste = AnnoncePlateforme.query.order_by(AnnoncePlateforme.date_publication.desc()).all()
    return render_template("plateforme/annonces.html", annonces=liste, ecoles=ecoles)


@plateforme_bp.route("/annonces/<int:annonce_id>/retirer", methods=["POST"])
@login_required
@super_admin_requis
def retirer_annonce(annonce_id):
    annonce = db.session.get(AnnoncePlateforme, annonce_id) or abort(404)
    annonce.active = False
    db.session.commit()
    flash("Annonce retirée.", "info")
    return redirect(url_for("plateforme.annonces"))


# ------------------------------------------------------------------ journal
@plateforme_bp.route("/journal")
@login_required
@super_admin_requis
def journal():
    """Journal de toutes les écoles, filtrable par école et par action."""
    from app.models.journal import JournalAction
    from app.services.pagination import paginer

    ecole_id = request.args.get("ecole_id", type=int)
    action = request.args.get("action", "").strip()
    requete = JournalAction.query.execution_options(**TOUS)
    if ecole_id:
        requete = requete.filter(JournalAction.ecole_id == ecole_id)
    if action:
        requete = requete.filter(JournalAction.action == action)
    page = paginer(requete.order_by(JournalAction.date_action.desc()))
    actions = sorted({a for (a,) in db.session.execute(select(JournalAction.action).distinct(), execution_options=TOUS)})
    ecoles = {e.id: e for e in db.session.query(Ecole).all()}
    return render_template("plateforme/journal.html", entrees=page, page=page, actions=actions, ecoles=ecoles,
                           filtre_ecole=ecole_id, filtre_action=action)


# ----------------------------------------------------------------- sauvegarde
@plateforme_bp.route("/<int:ecole_id>/sauvegarde")
@login_required
@super_admin_requis
def sauvegarde(ecole_id):
    """Sauvegarde complète d'une école, sans avoir à y entrer."""
    from app.sauvegarde.routes import construire_archive

    ecole = _ecole(ecole_id)
    ancien = (g.get("ecole_id"), g.get("ecole_obj"))
    g.ecole_id, g.ecole_obj = ecole.id, ecole
    try:
        tampon, nom_fichier = construire_archive()
    finally:
        g.ecole_id, g.ecole_obj = ancien
    _journaliser(ecole.id, "sauvegarde_exportee", f"{nom_fichier} (depuis la console de la plateforme)")
    db.session.commit()
    return send_file(tampon, as_attachment=True, download_name=nom_fichier, mimetype="application/zip")
