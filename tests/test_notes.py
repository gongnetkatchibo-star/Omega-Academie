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


def test_resaisir_une_note_la_corrige_sans_dupliquer(client, creer_utilisateur, creer_classe, creer_eleve, db):
    from app.models.note import Note

    classe = _preparer_enseignant(db, creer_utilisateur, creer_classe)
    eleve = creer_eleve("Eleve Test", classe)

    connecter(client, "prof@test.com")
    client.post(f"/notes/classe/{classe.id}", data={"matiere": "Français", "trimestre": "T1", f"note_{eleve.id}": "6"})
    assert Note.query.count() == 1
    assert Note.query.first().valeur == 6

    client.post(f"/notes/classe/{classe.id}", data={"matiere": "Français", "trimestre": "T1", f"note_{eleve.id}": "9"})
    assert Note.query.count() == 1, "une resaisie ne doit jamais créer une deuxième note"
    assert Note.query.first().valeur == 9


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
