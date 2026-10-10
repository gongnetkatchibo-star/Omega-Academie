"""Qui règle quoi dans la matrice des permissions (oct. 2026).

Règle : personne ne se sert soi-même, et personne ne donne ce qu'il n'a
pas. Chacun ne voit donc de la matrice que les lignes (rôles) placées
sous lui et les colonnes (modules) qu'il a le droit de confier :

- administrateur de la plateforme : tout ;
- fondateur : tous les rôles de l'école sauf le sien, pour les modules
  auxquels il a lui-même accès — jamais les zones techniques ;
- secrétaire : les rôles sans responsabilité de direction ni d'argent
  (enseignant, élève, parent…), pour les modules qui ne touchent pas
  aux finances.

Ce qui n'est pas dans la portée de quelqu'un n'est ni affiché, ni
modifié, ni effacé par lui."""

from app.models.permission import MODULES_CLES, MODULES_TECHNIQUES
from app.models.user import ROLES

# Rôles qui ouvrent l'écran des permissions.
ROLES_DELEGANTS = ("fondateur", "secretaire")

# Accès complet ou hors école : jamais dans la matrice d'une école.
_HORS_ECOLE = ("developpeur", "super_administrateur")

# Tout ce qui montre ou manipule de l'argent.
MODULES_FINANCIERS = ("finances", "caisse", "salaires", "statistiques")

# Ce que le secrétariat peut régler.
ROLES_DU_SECRETARIAT = ("responsable_pedagogique", "bibliothecaire", "enseignant", "personnel", "parent", "eleve")


def portee_matrice(role):
    """(rôles, modules) que `role` peut régler ; listes vides s'il n'a
    pas la main sur la matrice."""
    from app.services.modules_par_defaut import ROLES_PAR_DEFAUT
    from app.services.permissions import role_a_acces

    if role == "developpeur":
        return [r for r in ROLES if r != "developpeur"], list(MODULES_CLES)
    if role == "fondateur":
        roles = [r for r in ROLES if r not in _HORS_ECOLE and r != "fondateur"]
        modules = [
            m for m in MODULES_CLES
            if m not in MODULES_TECHNIQUES and role_a_acces("fondateur", m, ROLES_PAR_DEFAUT.get(m, []))
        ]
        return roles, modules
    if role == "secretaire":
        modules = [m for m in MODULES_CLES if m not in MODULES_TECHNIQUES and m not in MODULES_FINANCIERS]
        return list(ROLES_DU_SECRETARIAT), modules
    return [], []
