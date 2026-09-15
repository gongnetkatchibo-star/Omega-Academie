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


def moyenne_eleve(eleve, annee_scolaire=None):
    """Moyenne générale d'un élève (toutes matières et trimestres
    confondus, sur le barème de sa classe). None si aucune note saisie —
    on ne peut alors ni l'admettre ni l'échouer automatiquement."""
    requete = Note.query.filter_by(eleve_id=eleve.id)
    if annee_scolaire:
        requete = requete.filter_by(annee_scolaire=annee_scolaire)
    notes = requete.all()
    if not notes:
        return None
    return round(sum(n.valeur for n in notes) / len(notes), 2)


def a_reussi(eleve, annee_scolaire=None):
    """True/False, ou None si pas encore de notes (indéterminé)."""
    moyenne = moyenne_eleve(eleve, annee_scolaire)
    if moyenne is None:
        return None
    return moyenne >= seuil_reussite_pour_classe(eleve.classe)
