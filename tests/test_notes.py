"""Tests sur Notes — la resaisie ne doit jamais dupliquer une note, et
l'admission automatique doit strictement respecter le seuil de la
classe (Primaire 5/10, Collège 10/20)."""

from tests.conftest import connecter


def _preparer_enseignant(db, creer_utilisateur, creer_classe):
    from app.models.enseignant import Enseignant, Affectation

    ens_user = creer_utilisateur("Prof", "prof@test.com", "enseignant")
    classe = creer_classe()
    ens = Enseignant(user_id=ens_user.id, specialite="Français")
    db.session.add(ens)
    db.session.commit()
    db.session.add(Affectation(enseignant_id=ens.id, classe_id=classe.id, matiere="Français"))
    db.session.commit()
    return classe


def _creer_evaluation(client, classe, titre="Devoir 1", coefficient="1", type_evaluation="devoir", trimestre="T1"):
    from app.models.evaluation import Evaluation

    client.post(f"/notes/classe/{classe.id}", data={
        "matiere": "Français", "trimestre": trimestre, "titre": titre, "type": type_evaluation,
        "date": "2026-10-05", "coefficient": coefficient,
    })
    return Evaluation.query.filter_by(titre=titre).one().id


def test_resaisir_une_note_la_corrige_sans_dupliquer(client, creer_utilisateur, creer_classe, creer_eleve, db):
    from app.models.note import Note

    classe = _preparer_enseignant(db, creer_utilisateur, creer_classe)
    eleve = creer_eleve("Eleve Test", classe)

    connecter(client, "prof@test.com")
    evaluation_id = _creer_evaluation(client, classe)
    client.post(f"/notes/evaluation/{evaluation_id}", data={f"note_{eleve.id}": "6"})
    assert Note.query.count() == 1
    assert Note.query.first().valeur == 6

    client.post(f"/notes/evaluation/{evaluation_id}", data={f"note_{eleve.id}": "9"})
    assert Note.query.count() == 1, "une resaisie ne doit jamais créer une deuxième note"
    assert Note.query.first().valeur == 9

    # Case vidée : la note est retirée. Note hors barème : refusée.
    client.post(f"/notes/evaluation/{evaluation_id}", data={f"note_{eleve.id}": ""})
    assert Note.query.count() == 0
    r = client.post(f"/notes/evaluation/{evaluation_id}", data={f"note_{eleve.id}": "11"}, follow_redirects=True)
    assert Note.query.count() == 0 and "ignorée" in r.get_data(as_text=True)


def test_plusieurs_evaluations_et_moyenne_ponderee(client, creer_utilisateur, creer_classe, creer_eleve, db):
    """Devoir (coef. 1) = 4/10, composition (coef. 3) = 8/10 → moyenne 7/10."""
    from app.models.note import Note
    from app.services.bulletins import bulletins_de_la_classe

    classe = _preparer_enseignant(db, creer_utilisateur, creer_classe)
    eleve = creer_eleve("Eleve Test", classe)
    connecter(client, "prof@test.com")
    devoir = _creer_evaluation(client, classe, "Devoir 1", "1")
    composition = _creer_evaluation(client, classe, "Composition", "3", "composition")
    client.post(f"/notes/evaluation/{devoir}", data={f"note_{eleve.id}": "4"})
    client.post(f"/notes/evaluation/{composition}", data={f"note_{eleve.id}": "8"})

    assert Note.query.count() == 2
    calcul = bulletins_de_la_classe(classe, "T1", classe.annee_scolaire)
    assert calcul["bulletins"][eleve.id]["lignes"][0]["moyenne"] == 7
    page = client.get(f"/notes/classe/{classe.id}").get_data(as_text=True)
    assert "Devoir 1" in page and "Composition" in page and "1 / 1" in page

    client.post(f"/notes/evaluation/{composition}/supprimer")
    assert Note.query.count() == 1
    calcul = bulletins_de_la_classe(classe, "T1", classe.annee_scolaire)
    assert calcul["bulletins"][eleve.id]["lignes"][0]["moyenne"] == 4


def test_evaluation_reservee_a_l_enseignant_de_la_matiere(client, creer_utilisateur, creer_classe, creer_eleve, db):
    from app.models.enseignant import Enseignant, Affectation
    from flask import g

    classe = _preparer_enseignant(db, creer_utilisateur, creer_classe)
    autre = creer_utilisateur("Autre Prof", "autre@test.com", "enseignant")
    profil = Enseignant(user_id=autre.id)
    db.session.add(profil)
    db.session.flush()
    db.session.add(Affectation(enseignant_id=profil.id, classe_id=classe.id, matiere="Maths"))
    db.session.commit()
    connecter(client, "prof@test.com")
    evaluation_id = _creer_evaluation(client, classe)
    client.get("/auth/deconnexion")
    g.pop("_login_user", None)
    connecter(client, "autre@test.com")
    assert client.get(f"/notes/evaluation/{evaluation_id}").status_code == 403
    assert client.post(f"/notes/evaluation/{evaluation_id}/supprimer").status_code == 403


def test_anciennes_notes_rattachees_a_une_evaluation(app, db, creer_classe, creer_eleve):
    from app.models.note import Note
    from app.models.evaluation import Evaluation
    from app.services.evaluations import rattacher_notes_sans_evaluation

    classe = creer_classe()
    a, b = creer_eleve("A", classe, matricule="M1"), creer_eleve("B", classe, matricule="M2")
    for eleve, valeur in ((a, 6), (b, 8)):
        db.session.add(Note(eleve_id=eleve.id, classe_id=classe.id, matiere="Français", valeur=valeur, bareme=10,
                            trimestre="T1", annee_scolaire=classe.annee_scolaire))
    db.session.commit()
    assert rattacher_notes_sans_evaluation(app) == 2
    evaluation = Evaluation.query.one()
    assert evaluation.titre == "Note du trimestre" and len(evaluation.notes) == 2 and evaluation.ecole_id == 1
    assert rattacher_notes_sans_evaluation(app) == 0


def test_admission_automatique_refuse_sous_le_seuil(client, creer_utilisateur, creer_classe, creer_eleve, db):
    from app.models.note import Note
    from app.models.eleve import Eleve

    creer_utilisateur("Fond", "fond@test.com", "fondateur")
    cp1 = creer_classe(nom="CP1", niveau=1)
    creer_classe(nom="CP2", niveau=2)
    eleve = creer_eleve("Eleve Faible", cp1)
    db.session.add(Note(eleve_id=eleve.id, classe_id=cp1.id, matiere="Français", valeur=2, bareme=10, trimestre="T1", annee_scolaire=Eleve.annee_scolaire_courante()))
    db.session.commit()

    connecter(client, "fond@test.com")
    client.post(f"/eleves/{eleve.id}/passage", follow_redirects=True)

    db.session.refresh(eleve)
    assert eleve.classe.nom == "CP1", "un élève sous le seuil ne doit jamais passer"


def test_admission_automatique_valide_au_dessus_du_seuil(client, creer_utilisateur, creer_classe, creer_eleve, db):
    from app.models.note import Note
    from app.models.eleve import Eleve

    creer_utilisateur("Fond", "fond@test.com", "fondateur")
    cp1 = creer_classe(nom="CP1", niveau=1)
    creer_classe(nom="CP2", niveau=2)
    eleve = creer_eleve("Eleve Bon", cp1)
    db.session.add(Note(eleve_id=eleve.id, classe_id=cp1.id, matiere="Français", valeur=8, bareme=10, trimestre="T1", annee_scolaire=Eleve.annee_scolaire_courante()))
    db.session.commit()

    connecter(client, "fond@test.com")
    client.post(f"/eleves/{eleve.id}/passage", follow_redirects=True)

    db.session.refresh(eleve)
    assert eleve.classe.nom == "CP2"


def test_passage_bloque_sans_aucune_note(client, creer_utilisateur, creer_classe, creer_eleve, db):
    creer_utilisateur("Fond", "fond@test.com", "fondateur")
    cp1 = creer_classe(nom="CP1", niveau=1)
    creer_classe(nom="CP2", niveau=2)
    eleve = creer_eleve("Sans Notes", cp1)

    connecter(client, "fond@test.com")
    client.post(f"/eleves/{eleve.id}/passage", follow_redirects=True)

    db.session.refresh(eleve)
    assert eleve.classe.nom == "CP1", "sans note, impossible de décider — l'élève ne doit pas bouger"
