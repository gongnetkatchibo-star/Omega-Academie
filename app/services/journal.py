"""Journalisation centralisée des actions sensibles (sept. 2026).

Utilisation : appeler journaliser(...) juste avant le commit qui
effectue l'action — la ligne de journal fait partie de la même
transaction, donc elle ne peut jamais exister sans que l'action ait
réellement eu lieu, ni l'inverse."""

from flask_login import current_user

from app.extensions import db
from app.models.journal import JournalAction


def journaliser(action, details=None, cible_type=None, cible_id=None):
    utilisateur_id = current_user.id if current_user.is_authenticated else None
    db.session.add(JournalAction(
        utilisateur_id=utilisateur_id, action=action, details=details,
        cible_type=cible_type, cible_id=cible_id,
    ))
