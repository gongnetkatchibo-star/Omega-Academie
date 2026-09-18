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


def envoyer_email(destinataires, sujet, corps):
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

    destinataires = [d for d in destinataires if d]
    cle_api = current_app.config.get("BREVO_API_KEY")
    if not destinataires or not cle_api:
        return False

    expediteur_email = current_app.config.get("MAIL_DEFAULT_SENDER") or "no-reply@omega-academie.local"
    expediteur_nom = current_app.config.get("MAIL_DEFAULT_SENDER_NOM", "Omega Académie")

    corps_html = "<br>".join(ligne for ligne in corps.split("\n"))

    reussi = False
    try:
        reponse = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": cle_api, "Content-Type": "application/json", "accept": "application/json"},
            json={
                "sender": {"name": expediteur_nom, "email": expediteur_email},
                "to": [{"email": d} for d in destinataires],
                "subject": sujet,
                "htmlContent": corps_html,
                "textContent": corps,
            },
            timeout=10,
        )
        reussi = reponse.status_code in (200, 201)
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
            db.session.add(JournalEmail(
                destinataires=", ".join(destinataires), sujet=sujet, reussi=reussi,
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Échec de la journalisation d'un email.")
