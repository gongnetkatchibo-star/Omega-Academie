import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


def _url_base_de_donnees():
    """Render (et d'anciens hébergeurs comme Heroku) fournissent parfois
    une URL commençant par postgres:// — SQLAlchemy 1.4+ exige le préfixe
    postgresql://. On corrige automatiquement pour éviter une erreur de
    déploiement classique."""
    url = os.environ.get("DATABASE_URL")
    # Pilote psycopg2 imposé : SQLAlchemy 2.1 choisit sinon psycopg (v3),
    # absent de requirements.txt, et l'application ne démarre plus.
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url and url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url or "sqlite:///" + os.path.join(basedir, "instance", "app.db")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")
    SENTRY_DSN = os.environ.get("SENTRY_DSN")
    PLATEFORME_NOM = os.environ.get("PLATEFORME_NOM", "Toumaï Edu School")
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
    MAIL_DEFAULT_SENDER_NOM = os.environ.get("MAIL_DEFAULT_SENDER_NOM", "")

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

    # Cookies de session durcis (sept. 2026) :
    # - HTTPONLY : inaccessible en JavaScript, limite le vol de session par une faille XSS.
    # - SAMESITE=Lax : bloque l'envoi du cookie depuis un site tiers (protection CSRF supplémentaire).
    # - SECURE activé uniquement en production (HTTPS) — désactivé en dev, où il n'y a pas de HTTPS local.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False

    # Taille maximale d'un fichier envoyé (upload) — au-delà, Flask
    # refuse la requête automatiquement (erreur 413), avant même
    # d'atteindre le code de la route (sept. 2026). 20 Mo couvre
    # largement un document ou une photo de bonne qualité.
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024

    # Nombre de serveurs web placés devant l'application (nginx = 1).
    # Indispensable en production : sans cela l'application croit que
    # tous les visiteurs ont la même adresse (celle de nginx) et que le
    # site est en http. Laisser 0 quand l'application est jointe en direct.
    PROXY_COUCHES = int(os.environ.get("PROXY_COUCHES", "0"))

    # Compteur des tentatives de connexion. « memory:// » = un compteur
    # par processus ; indiquer une adresse Redis pour un compteur commun.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    # Durée pendant laquelle un processus garde les permissions en mémoire.
    PERMISSIONS_CACHE_SECONDES = int(os.environ.get("PERMISSIONS_CACHE_SECONDES", "20"))

    # PostgreSQL : vérifier une connexion avant de s'en servir (elle a pu
    # être coupée pendant une période calme) et la renouveler régulièrement.
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"pool_pre_ping": True, "pool_recycle": 1800}
        if SQLALCHEMY_DATABASE_URI.startswith("postgresql") else {}
    )

    # Jamais en production : un lien de réinitialisation ou un code affiché
    # à l'écran permettrait à n'importe qui de prendre un compte.
    AFFICHER_SECRETS_SANS_EMAIL = False
    # Code par email à chaque connexion du compte développeur (super-
    # administrateur) — à activer une fois l'envoi d'emails vérifié.
    DOUBLE_AUTH_DEVELOPPEUR = os.environ.get("DOUBLE_AUTH_DEVELOPPEUR", "").lower() in ("1", "oui", "true")

    # Déconnexion automatique après ce temps sans activité.
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get("SESSION_HEURES", "4")))
    # Blocage d'un compte après des mots de passe faux répétés.
    ECHECS_CONNEXION_MAX = 5
    BLOCAGE_MINUTES = 15


class DevelopmentConfig(Config):
    DEBUG = True
    # Sans service d'email, le code de vérification et le lien « mot de
    # passe oublié » s'affichent à l'écran — en développement uniquement.
    AFFICHER_SECRETS_SANS_EMAIL = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    """Utilisée uniquement par la suite de tests (pytest) — base en
    mémoire, jamais la vraie base, et CSRF désactivé pour ne pas avoir à
    extraire un jeton à chaque requête de test (sept. 2026)."""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    PERMISSIONS_CACHE_SECONDES = 0  # toujours relues : un test voit tout de suite ses changements
    AFFICHER_SECRETS_SANS_EMAIL = True


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
