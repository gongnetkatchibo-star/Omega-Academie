"""Tests de niveau : barème, décision automatique et inscription du
candidat admis dans la classe demandée."""

from app.extensions import db
from app.services.cycles import cycle_de_la_classe

# Primaire : note sur 10, admis à partir de 5.
# Collège et autres cycles : note sur 20, admis à partir de 10.
BAREMES = {"primaire": (10, 5), "college": (20, 10)}


def bareme(classe):
    """(note maximale, seuil d'admission) pour la classe demandée."""
    return BAREMES.get(cycle_de_la_classe(classe), BAREMES["college"])


def decision_pour_note(note, classe):
    note_max, seuil = bareme(classe)
    return "admis" if note >= seuil else "refuse"


def inscrire_candidat_admis(test):
    """Crée le dossier élève du candidat admis dans la classe demandée.
    Retourne l'élève créé, ou None si ce n'est pas possible (déjà inscrit,
    ou classe d'une autre année scolaire)."""
    from app.models.eleve import Eleve
    from app.models.historique import HistoriqueScolaire

    if test.eleve_id:
        return None
    classe = test.classe_demandee
    annee = Eleve.annee_scolaire_courante()
    if classe.annee_scolaire != annee:
        return None

    eleve = Eleve(
        matricule=Eleve.generer_matricule(classe),
        nom_complet=test.nom_candidat,
        classe_id=classe.id,
        date_naissance=test.date_naissance_candidat,
        sexe=test.sexe_candidat,
        telephone_parent=test.telephone_parent,
    )
    db.session.add(eleve)
    db.session.flush()
    eleve.actualiser_statut_dossier()
    db.session.add(HistoriqueScolaire(
        eleve_id=eleve.id, classe_id=classe.id, annee_scolaire=annee, resultat="en_cours",
    ))
    test.eleve_id = eleve.id
    return eleve
