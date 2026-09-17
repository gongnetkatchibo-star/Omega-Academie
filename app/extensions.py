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


def envoyer_email_securise(msg, delai_max=10):
    """Envoie un email avec un délai maximum strict.

    Sans ça, une connexion SMTP qui reste bloquée (réseau, pare-feu,
    serveur qui ne répond pas) fait attendre le serveur indéfiniment —
    jusqu'à ce que Render tue le processus de force (SIGKILL), plantant
    la page entière avec une "Internal Server Error", quelle que soit la
    boîte mail utilisée (constaté sept. 2026, worker timeout sur Render).

    Retourne True si l'envoi a réussi, False sinon (jamais d'exception
    qui remonte — un email qui ne part pas ne doit jamais faire planter
    la page)."""
    import socket

    ancien_delai = socket.getdefaulttimeout()
    socket.setdefaulttimeout(delai_max)
    try:
        mail.send(msg)
        return True
    except Exception:
        return False
    finally:
        socket.setdefaulttimeout(ancien_delai)
