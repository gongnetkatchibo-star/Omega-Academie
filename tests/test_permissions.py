"""Tests sur le contrôle d'accès — le point le plus sensible de
l'application : un rôle ne doit jamais voir ce qu'il n'a pas le droit
de voir, ni pouvoir modifier ce qu'il ne doit pas."""

from tests.conftest import connecter


def test_secretaire_na_pas_acces_finances_par_defaut(client, creer_utilisateur):
    creer_utilisateur("Secr", "secr@test.com", "secretaire")
    connecter(client, "secr@test.com")
    r = client.get("/finances/")
    assert r.status_code == 403


def test_developpeur_a_toujours_acces_complet(client, creer_utilisateur):
    creer_utilisateur("Dev", "dev@test.com", "developpeur")
    connecter(client, "dev@test.com")
    for route in ["/finances/", "/caisse/", "/salaires/", "/developpeur/"]:
        assert client.get(route).status_code == 200, f"{route} devrait être accessible au développeur"


def test_directeur_primaire_ne_voit_pas_le_college(client, creer_utilisateur, creer_classe, creer_eleve):
    creer_utilisateur("DirPrim", "dirprim@test.com", "directeur_primaire")
    cp1 = creer_classe(nom="CP1", niveau=1)
    sixieme = creer_classe(nom="6EME", niveau=7)
    creer_eleve("Eleve Primaire", cp1, matricule="OA26-TEST-PRIM")
    creer_eleve("Eleve College", sixieme, matricule="OA26-TEST-COLL")

    connecter(client, "dirprim@test.com")
    txt = client.get("/statistiques/").data.decode()
    assert "CP1" in txt
    assert "6EME" not in txt


def test_matrice_de_permissions_peut_accorder_un_acces(client, creer_utilisateur):
    creer_utilisateur("Dev", "dev@test.com", "developpeur")
    creer_utilisateur("Secr", "secr@test.com", "secretaire")

    # Par défaut, le secrétariat n'a pas accès aux salaires.
    connecter(client, "secr@test.com")
    assert client.get("/salaires/").status_code == 403
    client.get("/auth/deconnexion")

    # Le développeur accorde l'accès via la matrice de permissions.
    connecter(client, "dev@test.com")
    r = client.post("/developpeur/permissions/enregistrer", data={"secretaire__salaires": "on"}, follow_redirects=True)
    assert r.status_code == 200
    client.get("/auth/deconnexion")

    # Le secrétariat y a maintenant accès.
    connecter(client, "secr@test.com")
    assert client.get("/salaires/").status_code == 200


def test_parent_ne_voit_que_son_propre_enfant(client, creer_utilisateur, creer_classe, creer_eleve):
    parent1 = creer_utilisateur("Parent1", "p1@test.com", "parent")
    parent2 = creer_utilisateur("Parent2", "p2@test.com", "parent")
    classe = creer_classe()
    e1 = creer_eleve("Enfant1", classe, matricule="OA26-E1")
    e2 = creer_eleve("Enfant2", classe, matricule="OA26-E2")
    e1.parents.append(parent1)
    e2.parents.append(parent2)
    from app.extensions import db
    db.session.commit()

    connecter(client, "p1@test.com")
    assert client.get(f"/eleves/{e1.id}").status_code == 200
    assert client.get(f"/eleves/{e2.id}").status_code == 403
