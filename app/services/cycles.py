"""Scission des accès Direction par cycle (document complémentaire, §5,
sept. 2026) : un Directeur Primaire ne voit/gère que les classes CP à CM,
un Directeur Collège que les classes 6e à 3e. Fondateur et administrateur
général restent au-dessus de cette restriction (accès complet)."""

from app.services.moyennes import NIVEAU_LIMITE_PRIMAIRE

CYCLE_PAR_ROLE = {
    "directeur_primaire": "primaire",
    "directeur_college": "college",
}


def cycle_du_role(role):
    """None = pas de restriction de cycle (fondateur, administrateur_general...)."""
    return CYCLE_PAR_ROLE.get(role)


def cycle_de_la_classe(classe):
    return "primaire" if classe.niveau <= NIVEAU_LIMITE_PRIMAIRE else "college"


def classe_dans_le_cycle(classe, cycle):
    return cycle is None or cycle_de_la_classe(classe) == cycle


def filtrer_par_cycle(classes, cycle):
    if cycle is None:
        return classes
    return [c for c in classes if cycle_de_la_classe(c) == cycle]
