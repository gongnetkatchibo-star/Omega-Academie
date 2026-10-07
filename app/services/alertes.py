"""Alertes calculées à partir des données déjà présentes — pas besoin
d'IA pour repérer un élève en difficulté (sept. 2026)."""

from app.models.eleve import Eleve
from app.models.absence import Absence
from app.services.moyennes import moyennes_et_reussites, seuil_reussite_pour_classe

SEUIL_ABSENCES_INJUSTIFIEES = 3


def eleves_absences_frequentes(eleves, seuil=SEUIL_ABSENCES_INJUSTIFIEES):
    """Élèves ayant atteint ou dépassé `seuil` absences non justifiées
    (toutes périodes confondues, tant que l'absence existe en base)."""
    from collections import Counter

    # Une seule lecture pour toute l'école, puis comptage par élève.
    compte = Counter(a.eleve_id for a in Absence.query.filter_by(justifiee=False).all())
    resultat = []
    for e in eleves:
        nb = compte.get(e.id, 0)
        if nb >= seuil:
            resultat.append({"eleve": e, "nb_absences": nb})
    resultat.sort(key=lambda x: x["nb_absences"], reverse=True)
    return resultat


def eleves_moyenne_faible(eleves, annee):
    """Élèves dont la moyenne actuelle est sous le seuil de réussite de
    leur classe (Primaire < 5/10, Collège < 10/20) — exclut les élèves
    sans note (rien à évaluer)."""
    resultats = moyennes_et_reussites(eleves, annee)
    resultat = []
    for e in eleves:
        moyenne, reussi = resultats.get(e.id, (None, None))
        if moyenne is None:
            continue
        if not reussi:
            resultat.append({"eleve": e, "moyenne": moyenne, "seuil": seuil_reussite_pour_classe(e.classe)})
    resultat.sort(key=lambda x: x["moyenne"])
    return resultat
