"""Lien propre à chaque école : https://…/e/<identifiant>."""

from tests.conftest import connecter


def _ecole(db, nom="Lycée Toumaï de Pala", identifiant="lycee-toumai", **champs):
    from app.models.ecole import Ecole

    ecole = Ecole(nom=nom, sigle="LTP", ville="Pala", pays="Tchad", slogan="Savoir et discipline",
                  identifiant=identifiant, **champs)
    db.session.add(ecole)
    db.session.commit()
    return ecole


def test_identifiant_tire_du_nom_sans_accents_ni_doublon(app, db):
    from app.services.liens_ecole import identifiant_depuis, identifiant_libre, identifiant_valide

    assert identifiant_depuis("Lycée Toumaï de Pala") == "lycee-toumai-de-pala"
    assert identifiant_depuis("  École  N°1 — Kélo ") == "ecole-n1-kelo"
    assert identifiant_valide("lycee-toumai") and not identifiant_valide("ab") and not identifiant_valide("a--b")
    _ecole(db)
    assert identifiant_libre("Lycée Toumaï") == "lycee-toumai-2"
    assert identifiant_libre("Autre école") == "autre-ecole"


def test_la_page_de_l_ecole_montre_son_nom_et_habille_la_connexion(client, db):
    _ecole(db, logo=b"\x89PNG-faux", logo_mime="image/png")

    page = client.get("/e/lycee-toumai").get_data(as_text=True)
    assert "Lycée Toumaï de Pala" in page and "Savoir et discipline" in page
    assert "/e/lycee-toumai/logo" in page
    assert client.get("/e/lycee-toumai/logo").data == b"\x89PNG-faux"

    connexion = client.get("/auth/connexion").get_data(as_text=True)
    assert '<p class="nom-plateforme">Lycée Toumaï de Pala</p>' in connexion
    assert "connexion-logo" in connexion

    # L'accueil général fait oublier l'école.
    client.get("/")
    assert '<p class="nom-plateforme">Lycée Toumaï de Pala</p>' not in client.get("/auth/connexion").get_data(as_text=True)


def test_adresse_inconnue_ecole_suspendue_et_majuscules(client, db):
    ecole = _ecole(db)
    assert client.get("/e/nulle-part").status_code == 404
    assert client.get("/e/Lycee-Toumai").headers["Location"].endswith("/e/lycee-toumai")
    ecole.actif = False
    db.session.commit()
    assert client.get("/e/lycee-toumai").status_code == 404
    assert client.get("/e/lycee-toumai/logo").status_code == 404


def test_le_lien_n_ouvre_aucune_donnee_d_une_autre_ecole(client, db, creer_utilisateur, creer_classe, creer_eleve):
    """Suivre le lien d'une école puis se connecter avec un compte d'une
    autre : on arrive dans l'école du compte, jamais dans celle du lien."""
    autre = _ecole(db)
    creer_utilisateur("Amina Mahamat", "f@t.com", "fondateur")  # école de test (n° 1)
    classe = creer_classe(nom="CM1", niveau=5)
    creer_eleve("Fatimé Idriss", classe, sexe="F", matricule="ET26-CM1-001")

    client.get("/e/lycee-toumai")
    connecter(client, "f@t.com")
    assert client.get("/e/lycee-toumai").headers["Location"].endswith("/")  # déjà connecté : son tableau de bord
    page = client.get("/eleves/").get_data(as_text=True)
    assert "Fatimé Idriss" in page
    assert autre.nom not in client.get("/").get_data(as_text=True)


def test_la_deconnexion_ramene_a_la_connexion_de_son_ecole(client, db, creer_utilisateur):
    from app.models.ecole import Ecole

    ecole = db.session.get(Ecole, 1)
    ecole.identifiant = "ecole-test"
    db.session.commit()
    creer_utilisateur("Sec", "s@t.com", "secretaire")
    connecter(client, "s@t.com")
    page = client.get("/auth/deconnexion", follow_redirects=True).get_data(as_text=True)
    assert '<p class="nom-plateforme">École Test</p>' in page


def test_la_console_cree_l_adresse_et_refuse_un_doublon(client, db, creer_utilisateur):
    from app.models.ecole import Ecole

    _ecole(db)
    creer_utilisateur("Dev", "dev@t.com", "developpeur")
    connecter(client, "dev@t.com")
    base = {"sigle": "CSK", "ville": "Kélo", "pays": "Tchad", "fondateur_nom": "Fondateur",
            "fondateur_genre": "M", "fondateur_mot_de_passe": "motdepasse1"}

    # Champ vide : l'adresse vient du nom.
    client.post("/plateforme/nouvelle", data={**base, "nom": "Collège de Kélo", "prefixe_matricule": "CSK26",
                                              "fondateur_email": "a@k.td"})
    assert db.session.query(Ecole).filter_by(nom="Collège de Kélo").one().identifiant == "college-de-kelo"

    # Adresse déjà prise : refus, rien n'est créé.
    reponse = client.post("/plateforme/nouvelle", data={**base, "nom": "Autre", "prefixe_matricule": "AUT26",
                                                        "fondateur_email": "b@k.td", "identifiant": "Lycée Toumaï"})
    assert "déjà prise" in reponse.get_data(as_text=True)
    assert db.session.query(Ecole).filter_by(nom="Autre").first() is None

    # La console affiche le lien de chaque école.
    assert "/e/college-de-kelo" in client.get("/plateforme/").get_data(as_text=True)


def test_les_ecoles_existantes_recoivent_une_adresse_au_demarrage(app, db):
    from app.models.ecole import Ecole
    from app.services.liens_ecole import attribuer_identifiants_manquants

    _ecole(db, nom="École A", identifiant=None)
    _ecole(db, nom="École A", identifiant=None)
    attribuer_identifiants_manquants(app)
    adresses = {e.identifiant for e in db.session.query(Ecole).all()}
    assert {"ecole-test", "ecole-a", "ecole-a-2"} <= adresses
