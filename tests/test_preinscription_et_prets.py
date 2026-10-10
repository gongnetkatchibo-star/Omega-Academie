"""Pré-inscription en ligne et prêt de livres (oct. 2026)."""

from datetime import timedelta

import pytest

from tests.conftest import connecter


def _texte(r):
    return r.get_data(as_text=True)


def _aujourd_hui():
    from app.services.temps import aujourd_hui
    return aujourd_hui()


# ---------------------------------------------------------- pré-inscription
def _ouvrir_les_campagnes(db):
    from app.models.ecole import Ecole
    for ecole in db.session.query(Ecole).all():
        ecole.preinscriptions_ouvertes = True
    db.session.commit()


FORMULAIRE = {
    "nom_candidat": "Zara Mahamat", "sexe": "F", "date_naissance": "2018-03-04", "nom_parent": "Mahamat Ali",
    "telephone_parent": "66 12 34 56", "email_parent": "parent.zara@exemple.td", "message": "Merci",
}


def test_une_famille_pre_inscrit_sans_compte_et_le_secretariat_convoque(client, db, creer_utilisateur, creer_classe, monkeypatch):
    from app.models.preinscription import PreInscription
    from app.models.test_niveau import TestNiveau

    envois = []
    monkeypatch.setattr("app.extensions.envoyer_email", lambda d, s, c, **k: envois.append((d, s)) or True)
    monkeypatch.setattr("app.services.notifications.envoyer_email", lambda d, s, c, **k: envois.append((d, s)) or True)
    cp1 = creer_classe(nom="CP1", niveau=1)
    creer_utilisateur("Secrétaire", "sec@t.td", "secretaire")

    # Le lien n'est plus affiché au public : c'est l'administration qui le partage.
    assert "pré-inscription" not in _texte(client.get("/")).lower()
    _ouvrir_les_campagnes(db)
    r = client.get("/pre-inscriptions/demande")  # une seule école : directement son formulaire
    assert r.headers["Location"].endswith("/pre-inscriptions/demande/1")
    r = client.post("/pre-inscriptions/demande/1", data={**FORMULAIRE, "classe_demandee_id": cp1.id})
    demande = PreInscription.query.one()
    assert r.headers["Location"].endswith(f"/pre-inscriptions/merci/{demande.reference}")
    assert demande.ecole_id == 1 and demande.telephone_parent == "+23566123456"
    assert any("Nouvelle pré-inscription" in s for _, s in envois)

    connecter(client, "sec@t.td")
    assert "Zara Mahamat" in _texte(client.get("/pre-inscriptions/"))
    client.post(f"/pre-inscriptions/{demande.id}/convoquer", data={
        "classe_id": cp1.id, "date_test": (_aujourd_hui() + timedelta(days=3)).isoformat(), "heure": "08:00",
    })
    db.session.expire_all()
    assert demande.statut == "convoquee"
    test = TestNiveau.query.one()
    assert test.nom_candidat == "Zara Mahamat" and test.classe_demandee_id == cp1.id
    assert any(d == ["parent.zara@exemple.td"] and "convocation" in s for d, s in envois)
    # Une demande déjà traitée ne se convoque pas deux fois.
    client.post(f"/pre-inscriptions/{demande.id}/convoquer", data={"classe_id": cp1.id})
    assert TestNiveau.query.count() == 1


def test_hors_campagne_le_formulaire_est_ferme_et_l_administration_l_ouvre(client, db, creer_utilisateur):
    """Le lien n'est montré nulle part au public. Fermée, la campagne
    refuse toute demande, même avec le lien ; la direction l'ouvre, voit
    le lien à partager, puis la referme."""
    from app.models.ecole import Ecole
    from app.models.preinscription import PreInscription

    ecole = db.session.get(Ecole, 1)
    ecole.identifiant = "ecole-test"
    db.session.commit()

    assert "pré-inscription" not in _texte(client.get("/e/ecole-test")).lower()
    assert "Les pré-inscriptions sont fermées" in _texte(client.get("/pre-inscriptions/demande/1"))
    r = client.post("/pre-inscriptions/demande/1", data=FORMULAIRE)
    assert "Les pré-inscriptions sont fermées" in _texte(r) and PreInscription.query.count() == 0
    assert "/pre-inscriptions/demande/1" not in _texte(client.get("/pre-inscriptions/demande"))  # pas proposée dans la liste

    creer_utilisateur("Parent", "p@t.td", "parent")
    connecter(client, "p@t.td")
    assert client.post("/pre-inscriptions/campagne", data={"ouvrir": "1"}).status_code == 403
    client.get("/auth/deconnexion")

    creer_utilisateur("Secrétaire", "sec@t.td", "secretaire")
    connecter(client, "sec@t.td")
    page = _texte(client.get("/pre-inscriptions/"))
    assert "Ouvrir la campagne" in page and "/e/ecole-test/pre-inscription" not in page
    page = _texte(client.post("/pre-inscriptions/campagne", data={"ouvrir": "1"}, follow_redirects=True))
    assert "Fermer la campagne" in page and "/e/ecole-test/pre-inscription" in page and "wa.me" in page
    client.get("/auth/deconnexion")

    # Campagne ouverte : le lien partagé mène au formulaire.
    r = client.get("/e/ecole-test/pre-inscription")
    assert r.headers["Location"].endswith("/pre-inscriptions/demande/1")
    assert "Nom complet" in _texte(client.get("/pre-inscriptions/demande/1"))
    client.post("/pre-inscriptions/demande/1", data=FORMULAIRE)
    assert PreInscription.query.count() == 1

    connecter(client, "sec@t.td")
    client.post("/pre-inscriptions/campagne", data={"ouvrir": "0"})
    client.get("/auth/deconnexion")
    assert "Les pré-inscriptions sont fermées" in _texte(client.get("/pre-inscriptions/demande/1"))


def test_demande_invalide_ou_robot(client, db):
    from app.models.preinscription import PreInscription
    _ouvrir_les_campagnes(db)
    r = client.post("/pre-inscriptions/demande/1", data={**FORMULAIRE, "telephone_parent": "abc"})
    assert "Numéro de téléphone invalide" in _texte(r)
    client.post("/pre-inscriptions/demande/1", data={**FORMULAIRE, "site_web": "http://spam"})
    assert PreInscription.query.count() == 0
    assert client.get("/pre-inscriptions/demande/999").status_code == 404


def test_pre_inscription_rattachee_a_la_bonne_ecole(client, db, creer_utilisateur):
    from app.models.ecole import Ecole
    from app.models.preinscription import PreInscription
    db.session.add(Ecole(id=2, nom="École Deux", sigle="E2", prefixe_matricule="E226"))
    db.session.commit()
    _ouvrir_les_campagnes(db)
    client.post("/pre-inscriptions/demande/2", data=FORMULAIRE)
    demande = PreInscription.query.execution_options(tous_etablissements=True).one()
    assert demande.ecole_id == 2
    # Dans les tests, `g` survit d'une requête à l'autre : on rattache
    # explicitement le compte à l'école 1.
    creer_utilisateur("Secrétaire", "sec@t.td", "secretaire", ecole_id=1)
    connecter(client, "sec@t.td")
    assert "Zara" not in _texte(client.get("/pre-inscriptions/?statut=toutes"))
    demande_id = demande.id
    db.session.expunge_all()  # comme en production : rien de déjà chargé d'une autre école
    assert client.get(f"/pre-inscriptions/{demande_id}").status_code == 404


def test_refus_et_droits(client, db, creer_utilisateur, monkeypatch):
    from app.models.preinscription import PreInscription
    monkeypatch.setattr("app.services.notifications.envoyer_email", lambda *a, **k: True)
    _ouvrir_les_campagnes(db)
    client.post("/pre-inscriptions/demande/1", data=FORMULAIRE)
    demande = PreInscription.query.one()
    creer_utilisateur("Parent", "p@t.td", "parent")
    connecter(client, "p@t.td")
    assert client.get("/pre-inscriptions/").status_code == 403
    client.get("/auth/deconnexion")
    creer_utilisateur("Secrétaire", "sec@t.td", "secretaire")
    connecter(client, "sec@t.td")
    client.post(f"/pre-inscriptions/{demande.id}/refuser", data={"motif_refus": "Classe complète"})
    db.session.expire_all()
    assert demande.statut == "refusee" and demande.motif_refus == "Classe complète"


# ------------------------------------------------------------- prêt de livres
@pytest.fixture
def bibliotheque(db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.livre import Livre
    creer_utilisateur("Biblio", "b@t.td", "bibliothecaire")
    eleve = creer_eleve("Awa", creer_classe(nom="CM2", niveau=6), matricule="M1")
    parent = creer_utilisateur("Parent", "parent@t.td", "parent")
    eleve.parents.append(parent)
    livre = Livre(titre="Le Petit Prince", auteur="Saint-Exupéry", cote="R-12", exemplaires=1)
    db.session.add(livre)
    db.session.commit()
    return {"eleve": eleve, "livre": livre, "parent": parent}


def test_pret_retour_et_disponibilite(client, db, bibliotheque):
    from app.models.livre import Pret
    livre, eleve = bibliotheque["livre"], bibliotheque["eleve"]
    connecter(client, "b@t.td")
    assert "Le Petit Prince" in _texte(client.get("/bibliotheque/livres/"))
    client.post(f"/bibliotheque/livres/{livre.id}/preter", data={"emprunteur": f"e{eleve.id}"})
    pret = Pret.query.one()
    assert pret.date_retour_prevue == _aujourd_hui() + timedelta(days=14)
    # Un seul exemplaire : pas de deuxième prêt.
    client.post(f"/bibliotheque/livres/{livre.id}/preter", data={"emprunteur": f"e{eleve.id}"})
    assert Pret.query.count() == 1
    client.post(f"/bibliotheque/livres/pret/{pret.id}/retour")
    db.session.expire_all()
    assert pret.date_retour == _aujourd_hui() and livre.disponibles == 1


def test_retard_signale_et_relance_aux_parents(client, db, bibliotheque, monkeypatch):
    from app.models.livre import Pret
    envois = []
    monkeypatch.setattr("app.services.notifications.envoyer_email", lambda d, s, c, **k: envois.append(d) or True)
    passe = _aujourd_hui() - timedelta(days=20)
    pret = Pret(livre_id=bibliotheque["livre"].id, eleve_id=bibliotheque["eleve"].id, date_pret=passe,
                date_retour_prevue=passe + timedelta(days=14))
    db.session.add(pret)
    db.session.commit()
    connecter(client, "b@t.td")
    assert "Le Petit Prince" in _texte(client.get("/bibliotheque/livres/prets?retard=1"))
    client.post(f"/bibliotheque/livres/pret/{pret.id}/relancer")
    assert envois == [["parent@t.td"]]
    client.get("/auth/deconnexion")
    # Le parent voit le livre emprunté sur la fiche de son enfant.
    connecter(client, "parent@t.td")
    assert "Le Petit Prince" in _texte(client.get(f"/eleves/{bibliotheque['eleve'].id}"))
    assert client.get("/bibliotheque/livres/").status_code == 403


def test_livre_prete_ne_se_supprime_pas(client, db, bibliotheque):
    from app.models.livre import Livre, Pret
    livre = bibliotheque["livre"]
    db.session.add(Pret(livre_id=livre.id, eleve_id=bibliotheque["eleve"].id, date_pret=_aujourd_hui(),
                        date_retour_prevue=_aujourd_hui()))
    db.session.commit()
    connecter(client, "b@t.td")
    client.post(f"/bibliotheque/livres/{livre.id}/supprimer")
    assert Livre.query.count() == 1
