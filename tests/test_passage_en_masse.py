"""Passage de classe en masse vers l'année suivante."""

import pytest

from tests.conftest import connecter


@pytest.fixture
def fin_d_annee(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.note import Note
    from app.models.historique import HistoriqueScolaire

    creer_utilisateur("Sec", "s@t.com", "secretaire")
    cp1 = creer_classe(nom="CP1", niveau=1, annee="2025-2026")
    eleves = {}
    for nom, note in (("Bon", 8), ("Faible", 3), ("Sans Note", None)):
        e = creer_eleve(nom, cp1, matricule=f"M-{nom}")
        db.session.add(HistoriqueScolaire(eleve_id=e.id, classe_id=cp1.id, annee_scolaire="2025-2026", resultat="en_cours"))
        if note is not None:
            db.session.add(Note(eleve_id=e.id, classe_id=cp1.id, matiere="Lecture", valeur=note, bareme=10,
                                trimestre="T1", annee_scolaire="2025-2026"))
        eleves[nom] = e.id
    db.session.commit()
    connecter(client, "s@t.com")
    return {"cp1": cp1.id, **eleves}


def test_sans_annee_suivante_on_invite_a_la_creer(client, fin_d_annee):
    page = client.get(f"/eleves/passage-de-classe?classe_id={fin_d_annee['cp1']}").get_data(as_text=True)
    assert "Démarrer la nouvelle année scolaire" in page


def test_decisions_proposees_puis_appliquees(client, db, fin_d_annee, creer_classe):
    from app.models.eleve import Eleve
    from app.models.historique import HistoriqueScolaire

    cp1_suivant = creer_classe(nom="CP1", niveau=1, annee="2026-2027")
    cp2_suivant = creer_classe(nom="CP2", niveau=2, annee="2026-2027")
    cp1 = fin_d_annee["cp1"]

    page = client.get(f"/eleves/passage-de-classe?classe_id={cp1}").get_data(as_text=True)
    assert "8.00" in page and "3.00" in page and "Aucune note" in page
    for nom, attendu in (("Bon", "admis"), ("Faible", "redouble"), ("Sans Note", "rester")):
        bloc = page.split(f'name="decision_{fin_d_annee[nom]}"')[1].split("</select>")[0]
        assert f'value="{attendu}" selected' in bloc, nom

    r = client.post("/eleves/passage-de-classe", data={
        "classe_id": cp1, "annee_cible": "2026-2027",
        f"decision_{fin_d_annee['Bon']}": "admis", f"decision_{fin_d_annee['Faible']}": "redouble",
        f"decision_{fin_d_annee['Sans Note']}": "rester",
    }, follow_redirects=True)
    assert "1 élève(s) en classe supérieure, 1 redoublant(s), 0 sortant(s)" in r.get_data(as_text=True)

    db.session.expire_all()
    assert db.session.get(Eleve, fin_d_annee["Bon"]).classe_id == cp2_suivant.id
    assert db.session.get(Eleve, fin_d_annee["Faible"]).classe_id == cp1_suivant.id
    assert db.session.get(Eleve, fin_d_annee["Sans Note"]).classe_id == cp1
    resultats = {(h.eleve_id, h.annee_scolaire): h.resultat for h in HistoriqueScolaire.query.all()}
    assert resultats[(fin_d_annee["Bon"], "2025-2026")] == "admis"
    assert resultats[(fin_d_annee["Faible"], "2025-2026")] == "echec"
    assert resultats[(fin_d_annee["Bon"], "2026-2027")] == "en_cours"

    # Rejouer le même envoi ne déplace personne une deuxième fois.
    client.post("/eleves/passage-de-classe", data={
        "classe_id": cp1, "annee_cible": "2026-2027", f"decision_{fin_d_annee['Bon']}": "admis",
    })
    db.session.expire_all()
    assert db.session.get(Eleve, fin_d_annee["Bon"]).classe_id == cp2_suivant.id
    assert HistoriqueScolaire.query.filter_by(eleve_id=fin_d_annee["Bon"]).count() == 2


def test_fin_de_cycle_sortant(client, db, fin_d_annee, creer_classe):
    from app.models.eleve import Eleve

    creer_classe(nom="CP1", niveau=1, annee="2026-2027")  # pas de classe supérieure en 2026-2027
    page = client.get(f"/eleves/passage-de-classe?classe_id={fin_d_annee['cp1']}").get_data(as_text=True)
    bloc = page.split(f'name="decision_{fin_d_annee["Bon"]}"')[1].split("</select>")[0]
    assert 'value="sortant" selected' in bloc and 'value="admis"' not in bloc
    client.post("/eleves/passage-de-classe", data={
        "classe_id": fin_d_annee["cp1"], "annee_cible": "2026-2027", f"decision_{fin_d_annee['Bon']}": "sortant",
    })
    db.session.expire_all()
    assert db.session.get(Eleve, fin_d_annee["Bon"]).actif is False


def test_passage_reserve_a_la_gestion(client, creer_utilisateur):
    creer_utilisateur("Prof", "e@t.com", "enseignant")
    connecter(client, "e@t.com")
    assert client.get("/eleves/passage-de-classe").status_code == 403
