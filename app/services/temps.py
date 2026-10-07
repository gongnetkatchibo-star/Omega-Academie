"""Heure locale de l'école.

Le serveur tourne en temps universel ; l'école, elle, vit à l'heure du
Tchad (UTC+1). Toutes les dates que voient les utilisateurs — reçus,
absences, année scolaire, dates limites — partent d'ici."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

FUSEAU = os.environ.get("FUSEAU_HORAIRE", "Africa/Ndjamena")


def maintenant():
    """Date et heure locales, sans fuseau attaché (comme en base)."""
    try:
        return datetime.now(ZoneInfo(FUSEAU)).replace(tzinfo=None)
    except Exception:  # fuseau inconnu sur le serveur : on reste en temps universel
        return datetime.utcnow()


def aujourd_hui():
    return maintenant().date()
