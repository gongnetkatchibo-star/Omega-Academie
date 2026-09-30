"""Tests de niveau (admission automatique) et compte élève par matricule."""

from datetime import date

import pytest

from tests.conftest import connecter


def _texte(r):
    return r.get_data(as_text=True)


@pytest.fixture
def secretaire(client, creer_utilisateur):
    creer_utilisateur("Secrétaire", "sec@t.com", "secretaire")
    connecter(client, "sec@t.com")


def _creer_test(db, classe, nom="Candidat Test", telephone=None):
    from app.models.test_niveau import TestNiveau

    t = TestNiveau(nom_candidat=nom, sexe_candidat="F", date_naissance_candidat=date(2015, 3, 2),
                   telephone_parent=telephone, classe_demandee_id=classe.id, date_test=date.today())
    db.session.add(t)
    db.session.commit()
    return t.id


# ------------------------------------------------------------ admission

@pytest.mark.parametrize("niveau,note,admis", [
    (1, 5, True), (1, 4.75, False), (1, 10, True),      # primaire : /10, seuil 5
    (7, 10, True), (7, 9.5, False), (7, 20, True),      # collège : /20, seuil 10
])
def test_decision_automatique_selon_le_cycle(client, db, secretaire, creer_classe, niveau, note, admis):
    from app.models.test_niveau import TestNiveau
    from app.models.eleve import Eleve

    classe = creer_classe(nom="CLASSE", niveau=niveau)
    test_id = _creer_test(db, classe)
    client.post(f"/tests-niveau/{test_id}/decision", data={"note_obtenue": str(note)})
    db.session.expire_all()
    t = db.session.get(TestNiveau, test_id)
    assert t.decision == ("admis" if admis else "refuse")
    assert (Eleve.query.count() == 1) is admis


def test_admis_inscrit_dans_la_classe_demandee(client, db, secretaire, creer_classe):
    from app.models.test_niveau import TestNiveau
    from app.models.eleve import Eleve
    from app.models.historique import HistoriqueScolaire
    from app.models.user import User

    classe = creer_classe(nom="CE1", niveau=3)
    test_id = _creer_test(db, classe, nom="Awa Admise", telephone="+23566112233")
    r = client.post(f"/tests-niveau/{test_id}/decision", data={"note_obtenue": "7"}, follow_redirects=True)
    db.session.expire_all()

    eleve = Eleve.query.one()
    assert eleve.nom_complet == "Awa Admise" and eleve.classe_id == classe.id
    assert eleve.sexe == "F" and eleve.date_naissance == date(2015, 3, 2)
    assert eleve.telephone_parent == "+23566112233"
    assert eleve.matricule.startswith("ET26-CE1-")
    assert eleve.matricule in _texte(r)
    assert db.session.get(TestNiveau, test_id).eleve_id == eleve.id
    assert HistoriqueScolaire.query.filter_by(eleve_id=eleve.id).count() == 1
    assert User.query.filter_by(role="eleve").count() == 0  # plus de compte automatique


def test_pas_de_double_inscription_ni_de_changement_de_note(client, db, secretaire, creer_classe):
    from app.models.eleve import Eleve
    from app.models.test_niveau import TestNiveau

    classe = creer_classe(nom="CP1", niveau=1)
    test_id = _creer_test(db, classe)
    client.post(f"/tests-niveau/{test_id}/decision", data={"note_obtenue": "8"})
    db.session.expire_all()
    r = client.post(f"/tests-niveau/{test_id}/decision", data={"note_obtenue": "2"}, follow_redirects=True)
    db.session.expire_all()
    assert Eleve.query.count() == 1
    assert db.session.get(TestNiveau, test_id).note_obtenue == 8
    assert "déjà inscrit" in _texte(r)


@pytest.mark.parametrize("note", ["11", "-1", "", "abc"])
def test_note_hors_bareme_refusee(client, db, secretaire, creer_classe, note):
    from app.models.test_niveau import TestNiveau

    classe = creer_classe(nom="CP1", niveau=1)
    test_id = _creer_test(db, classe)
    r = client.post(f"/tests-niveau/{test_id}/decision", data={"note_obtenue": note}, follow_redirects=True)
    db.session.expire_all()
    assert db.session.get(TestNiveau, test_id).decision == "en_attente"
    assert "Note invalide" in _texte(r)


def test_classe_d_une_autre_annee_admis_sans_inscription(client, db, secretaire, creer_classe):
    from app.models.eleve import Eleve
    from app.models.test_niveau import TestNiveau

    ancienne = creer_classe(nom="CP1", niveau=1, annee="2020-2021")
    test_id = _creer_test(db, ancienne)
    client.post(f"/tests-niveau/{test_id}/decision", data={"note_obtenue": "9"})
    db.session.expire_all()
    assert db.session.get(TestNiveau, test_id).decision == "admis"
    assert Eleve.query.count() == 0


def test_nouveau_test_ne_propose_que_l_annee_en_cours(client, db, secretaire, creer_classe):
    creer_classe(nom="CM2", niveau=6)
    creer_classe(nom="VIEILLE", niveau=6, annee="2020-2021")
    page = _texte(client.get("/tests-niveau/nouveau"))
    assert "CM2 — note sur 10" in page
    assert "VIEILLE" not in page


def test_liste_affiche_bareme_et_lien_vers_l_eleve(client, db, secretaire, creer_classe):
    classe = creer_classe(nom="6e", niveau=7)
    test_id = _creer_test(db, classe)
    assert "/ 20" in _texte(client.get("/tests-niveau/"))
    client.post(f"/tests-niveau/{test_id}/decision", data={"note_obtenue": "14"})
    db.session.expire_all()
    page = _texte(client.get("/tests-niveau/"))
    assert "14/20" in page and "Inscrit — ET26-6E-001" in page


def test_inscription_manuelle_ne_cree_plus_de_compte(client, db, secretaire, creer_classe):
    from app.models.user import User

    classe = creer_classe(nom="CP1", niveau=1)
    client.post("/eleves/nouveau", data={"nom_complet": "Manuel", "classe_id": classe.id, "sexe": "M"})
    db.session.expire_all()
    assert User.query.filter_by(role="eleve").count() == 0


# ------------------------------------------------------------ compte élève

@pytest.fixture
def eleve_inscrit(db, creer_classe, creer_eleve):
    classe = creer_classe(nom="CM1", niveau=5)
    e = creer_eleve("Moussa Élève", classe, matricule="ET26-CM1-001")
    e.date_naissance = date(2014, 5, 20)
    db.session.commit()
    return e.id


def _inscrire(client, **champs):
    donnees = {"role": "eleve", "ecole_id": "1", "matricule": "et26-cm1-001",
               "date_naissance_eleve": "2014-05-20", "mot_de_passe": "eleve12345", "confirmation": "eleve12345"}
    donnees.update(champs)
    return client.post("/auth/inscription", data=donnees, follow_redirects=True)


def test_eleve_cree_son_compte_et_se_connecte_par_matricule(client, db, eleve_inscrit):
    from app.models.eleve import Eleve

    r = _inscrire(client)
    assert "Compte créé" in _texte(r)
    db.session.remove()
    eleve = db.session.get(Eleve, eleve_inscrit)
    assert eleve.compte is not None and eleve.compte.statut == "actif"
    assert eleve.compte.role == "eleve" and eleve.compte.nom_complet == "Moussa Élève"

    r = client.post("/auth/connexion", data={"email": "ET26-CM1-001", "mot_de_passe": "eleve12345"}, follow_redirects=True)
    assert "Moussa Élève" in _texte(r) and "Mon bulletin" in _texte(r)


def test_contact_facultatif_enregistre(client, db, eleve_inscrit):
    from app.models.eleve import Eleve

    _inscrire(client, email="Moussa@Mail.com", telephone="+23599001122")
    db.session.remove()
    compte = db.session.get(Eleve, eleve_inscrit).compte
    assert compte.email == "moussa@mail.com" and compte.telephone == "+23599001122"
    r = client.post("/auth/connexion", data={"email": "moussa@mail.com", "mot_de_passe": "eleve12345"}, follow_redirects=True)
    assert "Mon bulletin" in _texte(r)


def test_mauvaise_date_de_naissance_refusee(client, db, eleve_inscrit):
    from app.models.user import User

    r = _inscrire(client, date_naissance_eleve="2014-05-21")
    assert "Matricule ou date de naissance incorrect" in _texte(r)
    db.session.remove()
    assert User.query.filter_by(role="eleve").count() == 0


def test_matricule_inconnu_ou_d_une_autre_ecole_refuse(client, db, eleve_inscrit):
    from app.models.ecole import Ecole

    db.session.add(Ecole(id=2, nom="Autre", prefixe_matricule="AU26", actif=True))
    db.session.commit()
    assert "incorrect" in _texte(_inscrire(client, matricule="ET26-CM1-999"))
    assert "incorrect" in _texte(_inscrire(client, ecole_id="2"))


def test_un_seul_compte_par_matricule(client, db, eleve_inscrit):
    _inscrire(client)
    r = _inscrire(client, email="autre@t.com")
    assert "existe déjà pour ce matricule" in _texte(r)


def test_dossier_sans_date_de_naissance_passe_par_le_secretariat(client, db, creer_classe, creer_eleve):
    from app.models.eleve import Eleve

    e = creer_eleve("Sans Date", creer_classe(nom="CP2", niveau=2), matricule="ET26-CP2-001")
    eid = e.id
    r = _inscrire(client, matricule="ET26-CP2-001", date_naissance_eleve="2016-01-01")
    assert "secrétariat" in _texte(r)
    db.session.remove()
    assert db.session.get(Eleve, eid).compte.statut == "en_attente"
    r = client.post("/auth/connexion", data={"email": "ET26-CP2-001", "mot_de_passe": "eleve12345"}, follow_redirects=True)
    assert "en attente" in _texte(r)


def test_mot_de_passe_trop_court(client, db, eleve_inscrit):
    r = _inscrire(client, mot_de_passe="court", confirmation="court")
    assert "8 caractères" in _texte(r)


def test_formulaire_propose_le_profil_eleve(client):
    page = _texte(client.get("/auth/inscription"))
    assert 'value="eleve"' in page and 'name="matricule"' in page
    assert "Email ou matricule" in _texte(client.get("/auth/connexion"))
