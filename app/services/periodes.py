"""Découpage de l'année scolaire propre à chaque école (oct. 2026) :
trimestres (par défaut, comme jusqu'ici), semestres ou six séquences.

Chaque note garde le code de sa période (T1, S2, Q4…). La moyenne
annuelle est la moyenne des périodes notées, quel que soit le découpage."""

ANNUEL = "AN"

SYSTEMES = {
    "trimestres": [("T1", "1er trimestre"), ("T2", "2e trimestre"), ("T3", "3e trimestre")],
    "semestres": [("S1", "1er semestre"), ("S2", "2e semestre")],
    "sequences": [("Q1", "1re séquence"), ("Q2", "2e séquence"), ("Q3", "3e séquence"),
                  ("Q4", "4e séquence"), ("Q5", "5e séquence"), ("Q6", "6e séquence")],
}
LIBELLES_SYSTEMES = {
    "trimestres": "Trimestres (3 par an)",
    "semestres": "Semestres (2 par an)",
    "sequences": "Séquences (6 par an)",
}
SYSTEME_PAR_DEFAUT = "trimestres"
LIBELLES = {code: libelle for periodes in SYSTEMES.values() for code, libelle in periodes}
LIBELLES[ANNUEL] = "Année"
ORDRE = {code: rang for rang, code in enumerate(LIBELLES)}


def systeme_courant():
    """Découpage choisi par l'école en cours (trimestres sans réglage)."""
    try:
        from app.models.parametre import ParametreEtablissement
        from app.services.tenant import ecole_courante_id

        if ecole_courante_id() is None:
            return SYSTEME_PAR_DEFAUT
        systeme = ParametreEtablissement.get().systeme_periodes
    except Exception:  # hors requête (commande, script) : réglage par défaut
        return SYSTEME_PAR_DEFAUT
    return systeme if systeme in SYSTEMES else SYSTEME_PAR_DEFAUT


def periodes(systeme=None):
    """Codes des périodes de l'année, dans l'ordre (ex. ["T1", "T2", "T3"])."""
    return [code for code, _ in SYSTEMES[systeme or systeme_courant()]]


def periodes_et_annee(systeme=None):
    return periodes(systeme) + [ANNUEL]


def libelle(code):
    return LIBELLES.get(code, code)


def trier(codes):
    """Codes de période dans l'ordre de l'année (les inconnus à la fin)."""
    return sorted(set(codes), key=lambda c: (ORDRE.get(c, len(ORDRE)), c))
