"""Notifications automatiques par email — paiement enregistré, nouvelle
annonce (document complémentaire, sept. 2026).

Réutilise le même principe que le code 2FA et la réinitialisation de mot
de passe : envoi réel si MAIL_SERVER est configuré, sinon on se contente
de logguer (jamais d'erreur qui casserait l'action principale — une
notification ratée ne doit jamais empêcher un paiement d'être enregistré)."""

from flask import current_app
from flask_mail import Message

from app.extensions import mail


def notifier(destinataires, sujet, corps):
    """destinataires : liste d'emails (les entrées vides/None sont
    ignorées). Ne lève jamais d'exception — un échec d'envoi est
    seulement consigné dans les logs."""
    destinataires = [d for d in destinataires if d]
    if not destinataires or not current_app.config.get("MAIL_SERVER"):
        return False
    try:
        msg = Message(subject=sujet, recipients=destinataires, body=corps)
        mail.send(msg)
        return True
    except Exception:
        current_app.logger.exception("Échec de l'envoi d'une notification par email.")
        return False


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

    if annonce.destinataire == "tous":
        comptes = User.query.filter_by(statut="actif").all()
    else:
        comptes = User.query.filter_by(statut="actif", role=annonce.destinataire).all()

    destinataires = [u.email for u in comptes]
    corps = (
        f"Bonjour,\n\n"
        f"Une nouvelle annonce vient d'être publiée sur la plateforme :\n\n"
        f"{annonce.titre}\n\n"
        f"{annonce.contenu}\n\n"
        f"Connecte-toi à l'application pour plus de détails."
    )
    return notifier(destinataires, f"Nouvelle annonce — {annonce.titre}", corps)
