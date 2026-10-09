"""Réglages du serveur d'application (gunicorn), lus automatiquement
quand gunicorn est lancé depuis ce dossier :

    gunicorn run:app

Chaque valeur se change par une variable d'environnement, sans toucher
à ce fichier (voir deploiement/LISEZMOI.md)."""

import multiprocessing
import os

# gunicorn = serveur en ligne, toujours. Si le fichier .env du serveur
# contient encore FLASK_ENV=development (copie de .env.example), on
# passe quand même en production : en mode développement, les liens
# « mot de passe oublié » s'affichent à l'écran et le cookie de session
# voyage sans protection. (Pour développer : python3 run.py.)
if os.environ.get("FLASK_ENV") != "production":
    os.environ["FLASK_ENV"] = "production"

# Adresse d'écoute : locale par défaut, nginx fait le lien avec Internet.
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")

# Plusieurs processus, chacun avec plusieurs fils : une page lente (un
# PDF de bulletins, un export) ne bloque plus les autres utilisateurs.
# Par défaut 2 × cœurs + 1, plafonné à 5 ; WEB_CONCURRENCY pour changer.
workers = int(os.environ.get("WEB_CONCURRENCY", min(multiprocessing.cpu_count() * 2 + 1, 5)))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "4"))

# Les PDF d'une classe entière peuvent prendre du temps.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))

# Un processus est remplacé après un certain nombre de pages servies :
# la mémoire ne grossit pas indéfiniment.
max_requests = 2000
max_requests_jitter = 200

# Journaux sur la sortie standard : systemd (journalctl) les conserve.
accesslog = "-"
errorlog = "-"

# L'application est chargée une seule fois, avant de créer les
# processus : la création des tables et les mises à jour automatiques
# de la base au démarrage ne s'exécutent pas plusieurs fois en parallèle.
preload_app = True


def post_fork(server, worker):
    """Chaque processus ouvre ses propres connexions à la base, au lieu
    de partager celles ouvertes pendant le chargement."""
    from app.extensions import db
    from run import app

    with app.app_context():
        db.engine.dispose(close=False)
