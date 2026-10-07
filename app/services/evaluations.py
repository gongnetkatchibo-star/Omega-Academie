"""Évaluations : reprise des anciennes notes."""

from collections import defaultdict

from sqlalchemy import select

from app.extensions import db

TOUS = {"tous_etablissements": True}


def rattacher_notes_sans_evaluation(app):
    """Les notes saisies avant l'arrivée des évaluations (une seule note
    par matière et par trimestre) deviennent chacune la note d'une
    évaluation « Note du trimestre ». Sans effet s'il n'y en a plus."""
    from app.models.evaluation import Evaluation
    from app.models.note import Note

    orphelines = db.session.execute(
        select(Note).where(Note.evaluation_id.is_(None)).execution_options(**TOUS)
    ).scalars().all()
    if not orphelines:
        return 0

    groupes = defaultdict(list)
    for note in orphelines:
        groupes[(note.ecole_id, note.classe_id, note.matiere, note.trimestre, note.annee_scolaire)].append(note)

    for (ecole_id, classe_id, matiere, trimestre, annee), notes in groupes.items():
        dates = [n.date_saisie for n in notes if n.date_saisie]
        evaluation = Evaluation(
            ecole_id=ecole_id, classe_id=classe_id, matiere=matiere, trimestre=trimestre, annee_scolaire=annee,
            titre="Note du trimestre", type="devoir", coefficient=1,
            date=(min(dates).date() if dates else db.func.current_date()),
            enseignant_id=next((n.enseignant_id for n in notes if n.enseignant_id), None),
        )
        db.session.add(evaluation)
        db.session.flush()
        for note in notes:
            note.evaluation_id = evaluation.id
    db.session.commit()
    app.logger.info("%d note(s) rattachée(s) à %d évaluation(s)", len(orphelines), len(groupes))
    return len(orphelines)
