"""Mode SaaS : plusieurs établissements sur la même application.

Chaque test reproduit la production : `db.session.remove()` avant chaque
requête, pour que l'école B ne profite pas d'objets déjà chargés en
mémoire par le test (en production, chaque requête a sa propre session)."""

from datetime import date

import pytest
from flask import g

from tests.conftest import connecter


def _texte(reponse):
    return reponse.get_data().decode("utf-8", "ignore")


@pytest.fixture
def deux_ecoles(db, creer_utilisateur, creer_classe, creer_eleve):
    """École A (n°1) avec des données ; école B (n°2) avec son fondateur."""
    from app.models.ecole import Ecole
    from app.models.paiement import Paiement
    from app.models.mouvement_caisse import MouvementCaisse
    from app.models.ressource import Ressource
    from app.models.annonce import Annonce
    from app.models.message import Message
    from app.models.salaire import Salaire

    db.session.add(Ecole(id=2, nom="École Bêta", sigle="EB", ville="Moundou", pays="Tchad",
                         slogan="Devise Bêta", prefixe_matricule="EB26", actif=True))
    db.session.commit()

    fa = creer_utilisateur("Fondateur Alpha", "a@t.com", "fondateur")
    parent_a = creer_utilisateur("Parent Alpha", "pa@t.com", "parent")
    creer_utilisateur("Fondateur Beta", "b@t.com", "fondateur", ecole_id=2)
    classe_a = creer_classe(nom="CP1")
    eleve_a = creer_eleve("Awa Secret Alpha", classe_a)

    paiement = Paiement(eleve_id=eleve_a.id, montant=15000, mode="especes", echeance="inscription",
                        annee_scolaire=classe_a.annee_scolaire)
    mouvement = MouvementCaisse(date=date.today(), type="autre", libelle="Recette Secrete Alpha",
                                recette=5000, depense=0, automatique=False)
    ressource = Ressource(titre="Cours Secret Alpha", type="cours", nom_fichier="c.pdf",
                          contenu=b"%PDF-1.4 secret", type_mime="application/pdf",
                          consultation_sur_place=False)
    annonce = Annonce(titre="Annonce Secrete Alpha", contenu="x", destinataire="tous", auteur_id=fa.id)
    message = Message(parent_id=parent_a.id, auteur_id=parent_a.id, contenu="Message Secret Alpha")
    salaire = Salaire(personnel_id=fa.id, mois=1, annee=2026, montant=1)
    db.session.add_all([paiement, mouvement, ressource, annonce, message, salaire])
    db.session.commit()

    ids = {
        "fondateur_a": fa.id, "parent_a": parent_a.id, "classe_a": classe_a.id, "eleve_a": eleve_a.id,
        "paiement": paiement.id, "mouvement": mouvement.id, "ressource": ressource.id,
        "annonce": annonce.id, "salaire": salaire.id,
    }
    db.session.remove()
    return ids


URLS_DIRECTES = [
    "/eleves/{eleve_a}",
    "/finances/{eleve_a}",
    "/notes/bulletin/{eleve_a}",
    "/absences/eleve/{eleve_a}",
    "/documents/eleve/{eleve_a}/certificat",
    "/documents/eleve/{eleve_a}/attestation",
    "/caisse/recu/{mouvement}/pdf",
    "/bibliotheque/{ressource}/telecharger",
    "/communication/{annonce}",
    "/messagerie/{parent_a}",
    "/notes/classe/{classe_a}",
    "/emploi-du-temps/classe/{classe_a}",
]


@pytest.mark.parametrize("modele", URLS_DIRECTES)
def test_url_directe_vers_donnee_d_une_autre_ecole_introuvable(client, db, deux_ecoles, modele):
    connecter(client, "b@t.com")
    db.session.remove()
    r = client.get(modele.format(**deux_ecoles))
    assert r.status_code in (403, 404), f"{modele} → {r.status_code}"
    assert "Secret" not in _texte(r)
    assert "Alpha" not in _texte(r)


LISTES = ["/eleves/", "/classes/", "/finances/", "/caisse/", "/bibliotheque/", "/communication/",
          "/messagerie/", "/salaires/", "/statistiques/", "/developpeur/",
          "/eleves/export/pdf", "/", "/secretariat/demandes"]


@pytest.mark.parametrize("url", LISTES)
def test_listes_et_exports_ne_montrent_que_sa_propre_ecole(client, db, deux_ecoles, url):
    connecter(client, "b@t.com")
    db.session.remove()
    r = client.get(url, follow_redirects=True)
    assert r.status_code in (200, 403), f"{url} → {r.status_code}"
    texte = _texte(r)
    assert "Secret" not in texte and "Alpha" not in texte, url


def test_ecole_a_voit_toujours_ses_donnees(client, db, deux_ecoles):
    connecter(client, "a@t.com")
    db.session.remove()
    assert "Awa Secret Alpha" in _texte(client.get("/eleves/"))
    db.session.remove()
    assert client.get("/eleves/%d" % deux_ecoles["eleve_a"]).status_code == 200


def test_modification_et_suppression_croisees_refusees(client, db, deux_ecoles):
    from app.models.paiement import Paiement
    from app.models.mouvement_caisse import MouvementCaisse
    from app.models.ressource import Ressource

    connecter(client, "b@t.com")
    for url, donnees in [
        ("/finances/paiement/{paiement}/modifier", {"montant": "1"}),
        ("/finances/paiement/{paiement}/supprimer", {}),
        ("/caisse/mouvement/{mouvement}/supprimer", {}),
        ("/bibliotheque/{ressource}/supprimer", {}),
        ("/communication/{annonce}/supprimer", {}),
        ("/salaires/{salaire}/supprimer", {}),
        ("/developpeur/utilisateur/{fondateur_a}/verrouiller", {}),
    ]:
        db.session.remove()
        r = client.post(url.format(**deux_ecoles), data=donnees)
        assert r.status_code in (403, 404), f"{url} → {r.status_code}"

    db.session.remove()
    g.ecole_id = None
    tous = {"tous_etablissements": True}
    assert db.session.query(Paiement).execution_options(**tous).count() == 1
    assert float(db.session.query(Paiement).execution_options(**tous).one().montant) == 15000
    assert db.session.query(MouvementCaisse).execution_options(**tous).count() == 1
    assert db.session.query(Ressource).execution_options(**tous).count() == 1


def test_requete_en_masse_limitee_a_l_ecole_courante(app, db, deux_ecoles):
    from app.models.eleve import Eleve

    with app.test_request_context():
        g.ecole_id = 2
        assert Eleve.query.count() == 0
        assert db.session.get(Eleve, deux_ecoles["eleve_a"]) is None
        assert Eleve.query.update({"nom_complet": "PIRATE"}) == 0
        db.session.commit()
    db.session.remove()
    with app.test_request_context():
        g.ecole_id = 1
        assert db.session.get(Eleve, deux_ecoles["eleve_a"]).nom_complet == "Awa Secret Alpha"


def test_meme_nom_de_classe_dans_deux_ecoles(client, db, deux_ecoles):
    from app.models.classe import Classe

    from app.models.eleve import Eleve

    annee = Eleve.annee_scolaire_courante()
    connecter(client, "b@t.com")
    db.session.remove()
    client.post("/classes/nouvelle", data={"nom": "CP1", "niveau": "1", "annee_scolaire": annee}, follow_redirects=True)
    db.session.remove()
    g.ecole_id = None
    classes = db.session.query(Classe).execution_options(tous_etablissements=True).filter_by(nom="CP1").all()
    assert sorted(c.ecole_id for c in classes) == [1, 2]


def test_matricule_utilise_le_prefixe_de_l_ecole(app, db, deux_ecoles):
    from app.models.eleve import Eleve

    from app.models.classe import Classe

    classe = Classe(nom="CE1", niveau=3, annee_scolaire="2026-2027")
    with app.test_request_context():
        g.ecole_id = 2
        assert Eleve.generer_matricule(classe).startswith("EB26-CE1-")
    with app.test_request_context():
        g.ecole_id = 1
        assert Eleve.generer_matricule(classe).startswith("ET26-CE1-")


def test_identite_de_l_ecole_dans_l_interface(client, db, deux_ecoles):
    connecter(client, "b@t.com")
    db.session.remove()
    texte = _texte(client.get("/"))
    assert "École Bêta" in texte
    assert "Devise Bêta" in texte
    assert "École Test" not in texte


def test_ecole_suspendue_bloque_la_connexion(client, db, deux_ecoles):
    from app.models.ecole import Ecole

    connecter(client, "b@t.com")
    db.session.remove()
    ecole = db.session.get(Ecole, 2)
    ecole.actif = False
    db.session.commit()
    db.session.remove()
    r = client.get("/eleves/", follow_redirects=True)
    assert "suspendu" in _texte(r)
    db.session.remove()
    assert client.get("/eleves/").status_code == 302


def test_fondateur_ne_peut_pas_se_donner_le_role_developpeur(client, db, deux_ecoles):
    from app.models.user import User

    connecter(client, "b@t.com")
    db.session.remove()
    moi = db.session.query(User).execution_options(tous_etablissements=True).filter_by(email="b@t.com").one()
    moi_id = moi.id
    db.session.remove()
    client.post(f"/developpeur/utilisateur/{moi_id}", data={"role": "developpeur", "statut": "actif"})
    db.session.remove()
    g.ecole_id = None
    moi = db.session.query(User).execution_options(tous_etablissements=True).get(moi_id)
    assert moi.role != "developpeur"


# ---------------------------------------------------------------- console

def test_console_reservee_au_super_administrateur(client, db, deux_ecoles):
    connecter(client, "b@t.com")
    db.session.remove()
    assert client.get("/plateforme/").status_code == 403
    db.session.remove()
    assert client.post("/plateforme/2/basculer").status_code == 403


def test_super_admin_cree_une_ecole_et_son_fondateur(client, db, creer_utilisateur):
    from app.models.ecole import Ecole
    from app.models.user import User

    creer_utilisateur("Dev", "dev@t.com", "developpeur")
    connecter(client, "dev@t.com")
    db.session.remove()
    r = client.post("/plateforme/nouvelle", data={
        "nom": "Lycée Gamma", "sigle": "LG", "prefixe_matricule": "lg26", "ville": "Sarh", "pays": "Tchad",
        "slogan": "Savoir", "fondateur_nom": "Fondateur Gamma", "fondateur_email": "g@t.com",
        "fondateur_genre": "F", "fondateur_mot_de_passe": "gamma12345",
    }, follow_redirects=True)
    assert r.status_code == 200
    db.session.remove()
    ecole = Ecole.query.filter_by(nom="Lycée Gamma").one()
    assert ecole.prefixe_matricule == "LG26" and ecole.actif
    g.ecole_id = None
    fondateur = db.session.query(User).execution_options(tous_etablissements=True).filter_by(email="g@t.com").one()
    assert fondateur.ecole_id == ecole.id and fondateur.role == "fondateur"

    # Le nouveau fondateur se connecte et arrive dans SON école, vide.
    client.get("/auth/deconnexion")
    db.session.remove()
    connecter(client, "g@t.com", "gamma12345")
    db.session.remove()
    assert "Lycée Gamma" in _texte(client.get("/"))


def test_super_admin_refuse_prefixe_deja_pris(client, db, creer_utilisateur):
    from app.models.ecole import Ecole

    creer_utilisateur("Dev", "dev@t.com", "developpeur")
    connecter(client, "dev@t.com")
    db.session.remove()
    client.post("/plateforme/nouvelle", data={
        "nom": "Doublon", "sigle": "DB", "prefixe_matricule": "ET26", "fondateur_nom": "X",
        "fondateur_email": "x@t.com", "fondateur_genre": "M", "fondateur_mot_de_passe": "x12345678",
    })
    db.session.remove()
    assert Ecole.query.filter_by(nom="Doublon").count() == 0


def test_super_admin_entre_dans_une_ecole(client, db, deux_ecoles, creer_utilisateur):
    creer_utilisateur("Dev", "dev@t.com", "developpeur")
    connecter(client, "dev@t.com")
    db.session.remove()
    assert "Awa Secret Alpha" in _texte(client.get("/eleves/"))
    db.session.remove()
    client.post("/plateforme/2/entrer")
    db.session.remove()
    assert "Awa Secret Alpha" not in _texte(client.get("/eleves/"))


def test_inscription_rattache_le_compte_a_l_ecole_choisie(client, db, deux_ecoles):
    from app.models.user import User

    client.post("/auth/inscription", data={
        "nom_complet": "Nouvel Enseignant", "email": "np@t.com", "mot_de_passe": "np12345678",
        "confirmation": "np12345678", "confirmation_mot_de_passe": "np12345678",
        "role": "enseignant", "genre": "M", "ecole_id": "2",
    })
    db.session.remove()
    g.ecole_id = None
    u = db.session.query(User).execution_options(tous_etablissements=True).filter_by(email="np@t.com").first()
    assert u is not None and u.ecole_id == 2


def test_inscription_refuse_une_ecole_inexistante(client, db, deux_ecoles):
    from app.models.user import User

    client.post("/auth/inscription", data={
        "nom_complet": "Pirate", "email": "pi@t.com", "mot_de_passe": "pi12345678",
        "confirmation": "pi12345678", "confirmation_mot_de_passe": "pi12345678",
        "role": "enseignant", "genre": "M", "ecole_id": "999",
    })
    db.session.remove()
    g.ecole_id = None
    assert db.session.query(User).execution_options(tous_etablissements=True).filter_by(email="pi@t.com").first() is None


def test_ecrans_de_la_console_s_affichent(client, db, deux_ecoles, creer_utilisateur):
    creer_utilisateur("Dev", "dev@t.com", "developpeur")
    connecter(client, "dev@t.com")
    for url, attendu in [("/plateforme/", "École Bêta"), ("/plateforme/nouvelle", "Créer l'établissement"),
                         ("/plateforme/2/modifier", "Modifier École Bêta"), ("/developpeur/parametres", "École Test")]:
        db.session.remove()
        r = client.get(url)
        assert r.status_code == 200, url
        assert attendu in _texte(r).replace("&#39;", "'"), url
    db.session.remove()
    client.post("/plateforme/2/basculer")
    db.session.remove()
    from app.models.ecole import Ecole
    assert db.session.get(Ecole, 2).actif is False
