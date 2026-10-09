from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.connexion"
login_manager.login_message = "Connectez-vous pour accéder à cette page."
mail = Mail()

# Nombre de destinataires par appel à Brevo (qui en accepte 1000 au plus).
LOT_EMAILS = 500


def envoyer_email(destinataires, sujet, corps, nom_expediteur=None):
    """Envoie un email via l'API Brevo (HTTPS, port 443) — jamais via
    SMTP classique (ports 25/465/587), que Render bloque sur son plan
    gratuit depuis le 26 septembre 2025 (constaté sept. 2026, cause du
    blocage indéfini corrigé précédemment). Passer par une API web est
    la solution recommandée par Render lui-même dans cette situation.

    destinataires : liste d'emails. Ne lève jamais d'exception — un
    échec d'envoi ne doit jamais faire planter la page qui l'a demandé.
    Retourne True si l'envoi a réussi, False sinon (pas de clé API
    configurée, ou erreur réseau/authentification)."""
    import requests
    from flask import current_app

    # Sans doublon : un même compte ne reçoit jamais deux fois le message.
    # Les adresses techniques des comptes élèves (…@eleves.local) n'existent
    # pas : leur écrire ferait rebondir l'email et nuirait à la réputation
    # de l'expéditeur auprès du service d'envoi.
    destinataires = list(dict.fromkeys(
        d.strip() for d in destinataires if d and d.strip() and not d.strip().lower().endswith(".local")
    ))
    cle_api = current_app.config.get("BREVO_API_KEY")
    if not destinataires or not cle_api:
        return False

    expediteur_email = current_app.config.get("MAIL_DEFAULT_SENDER") or "no-reply@toumai-edu-school.local"
    from app.services.tenant import ecole_courante
    ecole = ecole_courante()
    expediteur_nom = nom_expediteur or (ecole.nom if ecole else None) or current_app.config.get("MAIL_DEFAULT_SENDER_NOM") or current_app.config.get("PLATEFORME_NOM")

    from markupsafe import escape
    corps_html = "<br>".join(str(escape(ligne)) for ligne in corps.split("\n"))

    reussi = False
    try:
        resultats = []
        for debut in range(0, len(destinataires), LOT_EMAILS):
            lot = destinataires[debut:debut + LOT_EMAILS]
            message = {
                "sender": {"name": expediteur_nom, "email": expediteur_email},
                "subject": sujet,
                "htmlContent": corps_html,
                "textContent": corps,
            }
            if len(lot) == 1:
                message["to"] = [{"email": lot[0]}]
            else:
                # Un exemplaire par personne : aucun destinataire ne voit
                # l'adresse des autres (une annonce part à tous les parents).
                message["messageVersions"] = [{"to": [{"email": d}]} for d in lot]
            reponse = requests.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": cle_api, "Content-Type": "application/json", "accept": "application/json"},
                json=message,
                timeout=20,
            )
            resultats.append(reponse.status_code in (200, 201, 202))
        reussi = all(resultats)
        return reussi
    except Exception:
        current_app.logger.exception("Échec de l'envoi d'un email via Brevo.")
        return False
    finally:
        # Journalisé quoi qu'il arrive (succès ou échec) — pour pouvoir
        # vérifier après coup ce qui est réellement parti en cas de
        # réclamation ("je n'ai rien reçu") ou d'incident (sept. 2026).
        try:
            from app.models.journal_email import JournalEmail
            liste = ", ".join(destinataires)
            if len(liste) > 500:  # taille de la colonne
                liste = f"{len(destinataires)} destinataires : {liste}"[:497] + "..."
            db.session.add(JournalEmail(destinataires=liste, sujet=sujet[:200], reussi=reussi))
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Échec de la journalisation d'un email.")
