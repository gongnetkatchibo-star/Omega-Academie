"""Niveaux de classe et cycles (oct. 2026).

Classe.niveau donne l'ordre du passage de classe : 1 à 6 pour le primaire
(CP1 à CM2), 7 à 10 pour le collège (6e à 3e), comme jusqu'ici. Une école
peut ajouter la maternelle (niveaux -2 à 0) et le lycée (11 à 13), avec
des séries. Pour les droits d'accès, la maternelle relève du directeur du
primaire et le lycée du directeur du collège ; les notes de maternelle
sont sur 10 comme au primaire, celles du lycée sur 20."""

NIVEAUX_MATERNELLE = [(-2, "Petite section"), (-1, "Moyenne section"), (0, "Grande section")]
NIVEAUX_PRIMAIRE_COLLEGE = list(enumerate(["CP1", "CP2", "CE1", "CE2", "CM1", "CM2", "6ème", "5ème", "4ème", "3ème"], start=1))
NIVEAUX_LYCEE = [(11, "2nde"), (12, "1ère"), (13, "Terminale")]
SERIES_PROPOSEES = ["A4", "A5", "C", "D", "E", "F", "G"]


def options_ecole():
    """(maternelle, lycée) proposés par l'école en cours."""
    try:
        from app.models.parametre import ParametreEtablissement
        parametre = ParametreEtablissement.get()
        return bool(parametre.cycle_maternelle), bool(parametre.cycle_lycee)
    except Exception:
        return False, False


def niveaux_disponibles():
    """[(niveau, nom)] proposés à la création d'une classe."""
    maternelle, lycee = options_ecole()
    return (NIVEAUX_MATERNELLE if maternelle else []) + NIVEAUX_PRIMAIRE_COLLEGE + (NIVEAUX_LYCEE if lycee else [])


def nom_du_cycle(niveau):
    if niveau <= 0:
        return "Maternelle"
    if niveau <= 6:
        return "Primaire"
    if niveau <= 10:
        return "Collège"
    return "Lycée"


def est_lycee(niveau):
    return niveau >= 11
