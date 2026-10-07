"""Calcul de moyenne et de réussite — utilisé à la fois par le module
Notes (barème de saisie) et par le module Statistiques (moyennes, taux de
réussite/échec), pour ne jamais avoir deux définitions différentes du
même calcul (§2 et §4 du document complémentaire, sept. 2026)."""

from app.models.note import Note

NIVEAU_LIMITE_PRIMAIRE = 6  # CP1 à CM2 = niveaux 1 à 6 ; Collège = 7+


def est_primaire(classe):
    return classe.niveau <= NIVEAU_LIMITE_PRIMAIRE


def bareme_pour_classe(classe):
    """Barème de saisie des notes : /10 au primaire, /20 au collège."""
    return 10 if est_primaire(classe) else 20


def seuil_reussite_pour_classe(classe):
    """Seuil d'admission/réussite (document complémentaire, §4) :
    Primaire moyenne >= 5/10 ; Collège moyenne >= 10/20."""
    return 5 if est_primaire(classe) else 10


TRIMESTRES = ["T1", "T2", "T3"]


def _classe_et_notes(eleve, annee_scolaire=None, classe=None):
    """Notes de l'élève dans sa classe de l'année demandée. Pour une
    année passée, la classe est celle où ses notes ont été saisies (sa
    classe actuelle n'est plus la bonne)."""
    requete = Note.query.filter_by(eleve_id=eleve.id)
    if annee_scolaire:
        requete = requete.filter_by(annee_scolaire=annee_scolaire)
    notes = requete.order_by(Note.id).all()
    if classe is None:
        if not notes or any(n.classe_id == eleve.classe_id for n in notes):
            classe = eleve.classe
        else:
            classe = notes[-1].classe
    return classe, [n for n in notes if n.classe_id == classe.id]


def _moyenne_annuelle(classe, notes):
    """Même calcul que le bulletin annuel (services/bulletins.py) : par
    trimestre, moyenne de chaque matière pondérée par le coefficient des
    évaluations, puis moyenne générale pondérée par le coefficient des
    matières ; l'année est la moyenne des trimestres notés."""
    from collections import defaultdict
    from app.models.bulletin import CoefficientMatiere
    from app.models.evaluation import Evaluation

    bareme = bareme_pour_classe(classe)
    coefficients = {
        c.matiere: c.coefficient for c in CoefficientMatiere.query.filter_by(classe_id=classe.id).all()
    }
    ids = {n.evaluation_id for n in notes if n.evaluation_id}
    poids_evaluation = (
        {e.id: e.coefficient for e in Evaluation.query.filter(Evaluation.id.in_(ids)).all()} if ids else {}
    )

    par_trimestre = {t: defaultdict(list) for t in TRIMESTRES}
    for n in notes:
        if n.trimestre in par_trimestre and n.bareme:
            par_trimestre[n.trimestre][n.matiere].append(
                (n.valeur * bareme / n.bareme, poids_evaluation.get(n.evaluation_id, 1) or 1)
            )

    generales = []
    for trimestre in TRIMESTRES:
        total = poids = 0.0
        for matiere, valeurs in par_trimestre[trimestre].items():
            poids_notes = sum(c for _, c in valeurs)
            if not poids_notes:
                continue
            moyenne = round(sum(v * c for v, c in valeurs) / poids_notes, 2)
            coefficient = coefficients.get(matiere, 1)
            total += moyenne * coefficient
            poids += coefficient
        if poids:
            generales.append(round(total / poids, 2))
    return round(sum(generales) / len(generales), 2) if generales else None


def moyenne_et_reussite(eleve, annee_scolaire=None, classe=None):
    """(moyenne annuelle, a réussi) — (None, None) sans note : on ne peut
    alors ni admettre ni faire échouer l'élève automatiquement."""
    classe, notes = _classe_et_notes(eleve, annee_scolaire, classe)
    moyenne = _moyenne_annuelle(classe, notes) if notes else None
    if moyenne is None:
        return None, None
    return moyenne, moyenne >= seuil_reussite_pour_classe(classe)


def moyenne_eleve(eleve, annee_scolaire=None, classe=None):
    """Moyenne annuelle de l'élève sur le barème de sa classe — la même
    que celle de son bulletin annuel. None si aucune note saisie."""
    return moyenne_et_reussite(eleve, annee_scolaire, classe)[0]


def a_reussi(eleve, annee_scolaire=None, classe=None):
    """True/False, ou None si pas encore de notes (indéterminé)."""
    return moyenne_et_reussite(eleve, annee_scolaire, classe)[1]
