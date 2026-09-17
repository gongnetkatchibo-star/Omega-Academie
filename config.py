import os

basedir = os.path.abspath(os.path.dirname(__file__))


def _url_base_de_donnees():
    """Render (et d'anciens hébergeurs comme Heroku) fournissent parfois
    une URL commençant par postgres:// — SQLAlchemy 1.4+ exige le préfixe
    postgresql://. On corrige automatiquement pour éviter une erreur de
    déploiement classique."""
    url = os.environ.get("DATABASE_URL")
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url or "sqlite:///" + os.path.join(basedir, "instance", "app.db")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")
    SQLALCHEMY_DATABASE_URI = _url_base_de_donnees()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Envoi d'email (réinitialisation de mot de passe, notifications).
    # Non renseigné = aucun envoi réel : le lien de réinitialisation reste
    # affiché à l'écran (voir app/auth/routes.py).
    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", MAIL_USERNAME)
    MAIL_DEFAULT_SENDER_NOM = os.environ.get("MAIL_DEFAULT_SENDER_NOM", "Omega Académie")

    # Envoi d'email via l'API Brevo (HTTPS) — remplace le SMTP classique,
    # bloqué par Render sur son plan gratuit (sept. 2026).
    BREVO_API_KEY = os.environ.get("BREVO_API_KEY")

    # Format officiel des matricules pour l'année scolaire en cours,
    # fourni par la direction (fiche 2026-2027) : OA26-CLASSE-XXX.
    # À mettre à jour chaque rentrée (ex. "OA27" pour 2027-2028).
    MATRICULE_PREFIXE = os.environ.get("MATRICULE_PREFIXE", "OA26")

    # Assistant IA (document complémentaire, §6) : laisser vide = mode
    # sans IA générative (réponses sur les données autorisées, aucun
    # coût). Renseigner une clé pour activer un vrai modèle plus tard.
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
