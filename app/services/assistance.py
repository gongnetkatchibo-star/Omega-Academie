"""Demandes d'assistance entre une école et l'administration de la
plateforme (oct. 2026) : une conversation par demande, notifiée par
email de part et d'autre."""

from flask import url_for
from sqlalchemy import select

from app.extensions import db
from app.models.gouvernance import DemandeSupport, MessageSupport
from app.services.temps import maintenant

TOUS = {"tous_etablissements": True}


def emails_plateforme():
    from flask import current_app
    from app.models.user import User

    emails = [u.email for u in db.session.execute(
        select(User).where(User.role == "developpeur", User.statut == "actif"), execution_options=TOUS,
    ).scalars().all() if u.email]
    supplementaire = current_app.config.get("PLATEFORME_EMAIL_SUPPORT")
    if supplementaire:
        emails.append(supplementaire)
    return sorted(set(emails))


def ajouter_message(demande, auteur, contenu, de_la_plateforme):
    demande.messages.append(MessageSupport(auteur_id=auteur.id, contenu=contenu, de_la_plateforme=de_la_plateforme))
    demande.date_maj = maintenant()
    if de_la_plateforme:
        demande.non_lu_ecole, demande.non_lu_plateforme = True, False
        if demande.statut == "ouverte":
            demande.statut = "en_cours"
    else:
        demande.non_lu_plateforme, demande.non_lu_ecole = True, False
        if demande.statut == "resolue":
            demande.statut = "ouverte"  # l'école relance : la demande se rouvre


def notifier(demande, de_la_plateforme, contenu):
    from app.services.notifications import notifier as envoyer
    from app.services.abonnements import destinataires_direction

    if de_la_plateforme:
        destinataires = destinataires_direction(demande.ecole_id)
        if demande.auteur and demande.auteur.email and demande.auteur.email not in destinataires:
            destinataires.append(demande.auteur.email)
        lien = url_for("gouvernance.demande", demande_id=demande.id, _external=True)
        entete = "L'administration de la plateforme a répondu à votre demande"
    else:
        destinataires = emails_plateforme()
        lien = url_for("plateforme.demande", demande_id=demande.id, _external=True)
        entete = f"Nouveau message de {demande.ecole.nom}"
    if not destinataires:
        return False
    extrait = contenu if len(contenu) <= 600 else contenu[:600] + "…"
    return envoyer(destinataires, f"[Assistance] {demande.sujet}", f"{entete} :\n\n{extrait}\n\nLire et répondre : {lien}")


def non_lues_ecole(ecole_id):
    return DemandeSupport.query.filter_by(ecole_id=ecole_id, non_lu_ecole=True).count() if ecole_id else 0


def non_lues_plateforme():
    return DemandeSupport.query.filter_by(non_lu_plateforme=True).count()
