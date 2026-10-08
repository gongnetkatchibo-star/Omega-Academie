"""Qui peut suivre un élève (cahier de textes, discipline, emploi du
temps, absences) : sa famille, lui-même, ses enseignants, et la
direction de son cycle selon la matrice des permissions."""

from datetime import datetime

from flask import request
from flask_login import current_user

from app.services.cycles import cycle_du_role, classe_dans_le_cycle
from app.services.temps import aujourd_hui

DIRECTION = ["directeur_primaire", "directeur_college", "fondateur", "administrateur_general"]


def est_famille(eleve):
    """Parent rattaché, ou l'élève lui-même."""
    if current_user in eleve.parents:
        return True
    return current_user.role == "eleve" and eleve.user_id == current_user.id


def classes_de_l_enseignant():
    """Identifiants des classes où enseigne le compte connecté."""
    if current_user.role != "enseignant" or not current_user.profil_enseignant:
        return set()
    return {a.classe_id for a in current_user.profil_enseignant.affectations}


def matieres_dans(classe_id):
    profil = current_user.profil_enseignant if current_user.role == "enseignant" else None
    if not profil:
        return []
    return sorted({a.matiere for a in profil.affectations if a.classe_id == classe_id})


def supervise(classe, module, roles_par_defaut):
    """La direction (ou un rôle autorisé par la matrice) voit la classe,
    dans la limite de son cycle."""
    from app.services.permissions import role_a_acces

    if current_user.role == "developpeur":
        return True
    if not role_a_acces(current_user.role, module, roles_par_defaut):
        return False
    cycle = cycle_du_role(current_user.role)
    return not cycle or classe_dans_le_cycle(classe, cycle)


def peut_suivre(eleve, module, roles_par_defaut):
    return (
        est_famille(eleve)
        or eleve.classe_id in classes_de_l_enseignant()
        or supervise(eleve.classe, module, roles_par_defaut)
    )


def date_du_formulaire(nom, facultative=False):
    """Date AAAA-MM-JJ lue dans le formulaire. Vide ou invalide : None si
    elle est facultative, sinon la date du jour."""
    valeur = (request.form.get(nom) or request.args.get(nom) or "").strip()
    try:
        return datetime.strptime(valeur, "%Y-%m-%d").date()
    except ValueError:
        return None if facultative else aujourd_hui()
