"""Permissions dynamiques par rôle et par module — modifiables depuis
l'espace développeur (document complémentaire, sept. 2026).

Principe : chaque module protégé a une liste de rôles par défaut, codée
dans son propre fichier de routes (comme avant). Cette liste ne change
JAMAIS toute seule. Mais si le développeur a explicitement activé ou
désactivé un module pour un rôle depuis la matrice de permissions, cette
décision prend le dessus sur la valeur par défaut — pour CE rôle et CE
module précisément, sans toucher au reste.
"""

import time

from flask import current_app

from app.models.permission import Permission

# Les permissions sont relues en base au plus toutes les N secondes
# (PERMISSIONS_CACHE_SECONDES) : chaque processus du serveur garde sa
# propre copie, et un changement fait dans l'un doit atteindre les
# autres sans redémarrage. Auparavant la copie n'était jamais relue une
# fois remplie — et relue à CHAQUE vérification tant qu'elle était vide.
_CLE = "permissions_cache"


def _charger():
    etat = current_app.extensions.get(_CLE)
    duree = current_app.config.get("PERMISSIONS_CACHE_SECONDES", 20)
    if etat is None or time.monotonic() - etat["lu_le"] >= duree:
        etat = {
            "lu_le": time.monotonic(),
            "valeurs": {(p.role, p.module): p.autorise for p in Permission.query.all()},
        }
        current_app.extensions[_CLE] = etat
    return etat["valeurs"]


def vider_cache():
    current_app.extensions.pop(_CLE, None)


def role_a_acces(role, module, roles_par_defaut):
    """True/False selon : une permission explicite existe pour ce couple
    (role, module) ? Sinon, comportement d'origine (role in
    roles_par_defaut). Le développeur garde toujours un accès complet,
    quoi qu'il arrive — ce n'est jamais lui qui se couperait l'accès par
    erreur depuis cette matrice."""
    if role == "developpeur":
        return True
    overrides = _charger()
    cle = (role, module)
    if cle in overrides:
        return overrides[cle]
    return role in roles_par_defaut


def toutes_les_permissions(roles, modules):
    """Pour l'écran de la matrice : l'état actuel (effectif) de chaque
    couple (rôle, module), qu'il vienne d'une permission explicite ou de
    la valeur par défaut du module."""
    from app.services.modules_par_defaut import ROLES_PAR_DEFAUT

    etat = {}
    for role in roles:
        for module in modules:
            defaut = ROLES_PAR_DEFAUT.get(module, [])
            etat[(role, module)] = role_a_acces(role, module, defaut)
    return etat
