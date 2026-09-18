"""Notifications automatiques par email — paiement enregistré, nouvelle
annonce (document complémentaire, sept. 2026).

Envoyées via l'API Brevo (voir app/extensions.py) — jamais SMTP, bloqué
par Render sur son plan gratuit. Ne lève jamais d'exception : une
notification ratée ne doit jamais empêcher un paiement d'être enregistré."""

from app.extensions import envoyer_email


def notifier(destinataires, sujet, corps):
    """destinataires : liste d'emails (les entrées vides/None sont
    ignorées)."""
    return envoyer_email(destinataires, sujet, corps)


def notifier_paiement(paiement, eleve):
    destinataires = [p.email for p in eleve.parents]
    if not destinataires:
        return False
    from app.models.paiement import LIBELLES_ECHEANCE
    corps = (
        f"Bonjour,\n\n"
        f"Un paiement vient d'être enregistré pour {eleve.nom_complet} :\n"
        f"- Échéance : {LIBELLES_ECHEANCE[paiement.echeance]}\n"
        f"- Montant : {paiement.montant:.0f}\n"
        f"- Reçu : {paiement.numero_recu}\n"
        f"- Date : {paiement.date_paiement.strftime('%d/%m/%Y')}\n\n"
        f"Ceci est une confirmation automatique — aucune action n'est nécessaire."
    )
    return notifier(destinataires, f"Paiement enregistré — {eleve.nom_complet}", corps)


def notifier_annonce(annonce):
    from app.models.user import User
    from flask import url_for

    if annonce.destinataire == "tous":
        comptes = User.query.filter_by(statut="actif").all()
    else:
        comptes = User.query.filter_by(statut="actif", role=annonce.destinataire).all()

    destinataires = [u.email for u in comptes]
    lien = url_for("communication.detail", annonce_id=annonce.id, _external=True)
    corps = (
        f"Bonjour,\n\n"
        f"Une nouvelle annonce vient d'être publiée sur la plateforme :\n\n"
        f"{annonce.titre}\n\n"
        f"{annonce.contenu}\n\n"
        f"Voir plus : {lien}"
    )
    return notifier(destinataires, f"Nouvelle annonce — {annonce.titre}", corps)
