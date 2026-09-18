"""Alertes calculées à partir des données déjà présentes — pas besoin
d'IA pour repérer un élève en difficulté (sept. 2026)."""

from app.models.eleve import Eleve
from app.models.absence import Absence
from app.services.moyennes import moyenne_eleve, a_reussi, seuil_reussite_pour_classe

SEUIL_ABSENCES_INJUSTIFIEES = 3


def eleves_absences_frequentes(eleves, seuil=SEUIL_ABSENCES_INJUSTIFIEES):
    """Élèves ayant atteint ou dépassé `seuil` absences non justifiées
    (toutes périodes confondues, tant que l'absence existe en base)."""
    resultat = []
    for e in eleves:
        nb = Absence.query.filter_by(eleve_id=e.id, justifiee=False).count()
        if nb >= seuil:
            resultat.append({"eleve": e, "nb_absences": nb})
    resultat.sort(key=lambda x: x["nb_absences"], reverse=True)
    return resultat


def eleves_moyenne_faible(eleves, annee):
    """Élèves dont la moyenne actuelle est sous le seuil de réussite de
    leur classe (Primaire < 5/10, Collège < 10/20) — exclut les élèves
    sans note (rien à évaluer)."""
    resultat = []
    for e in eleves:
        moyenne = moyenne_eleve(e, annee)
        if moyenne is None:
            continue
        if not a_reussi(e, annee):
            resultat.append({"eleve": e, "moyenne": moyenne, "seuil": seuil_reussite_pour_classe(e.classe)})
    resultat.sort(key=lambda x: x["moyenne"])
    return resultat
