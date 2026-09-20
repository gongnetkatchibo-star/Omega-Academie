"""Tests sur la messagerie parent-école et le rappel de sauvegarde."""

from tests.conftest import connecter


def test_parent_peut_envoyer_et_relire_son_message(client, creer_utilisateur):
    creer_utilisateur("Parent", "parent@test.com", "parent")
    connecter(client, "parent@test.com")

    client.post("/messagerie/envoyer", data={"contenu": "Question sur les frais."})
    r = client.get("/messagerie/")
    assert "Question sur les frais." in r.data.decode()


def test_ecole_voit_et_repond_au_fil_dun_parent(client, creer_utilisateur):
    creer_utilisateur("Secr", "secr@test.com", "secretaire")
    parent = creer_utilisateur("Parent", "parent@test.com", "parent")

    connecter(client, "parent@test.com")
    client.post("/messagerie/envoyer", data={"contenu": "Bonjour"})
    client.get("/auth/deconnexion")

    connecter(client, "secr@test.com")
    r = client.get("/messagerie/")
    assert "Parent" in r.data.decode() and "1 non lu" in r.data.decode()

    client.post(f"/messagerie/{parent.id}/repondre", data={"contenu": "Réponse de l'école"})
    client.get("/auth/deconnexion")

    connecter(client, "parent@test.com")
    r = client.get("/messagerie/")
    assert "Réponse de l" in r.data.decode() and "cole" in r.data.decode()


def test_parent_ne_peut_pas_ouvrir_le_fil_dun_autre(client, creer_utilisateur):
    p1 = creer_utilisateur("Parent Un", "p1@test.com", "parent")
    creer_utilisateur("Parent Deux", "p2@test.com", "parent")

    connecter(client, "p2@test.com")
    r = client.get(f"/messagerie/{p1.id}")
    assert r.status_code == 403


def test_rappel_de_sauvegarde_absent_apres_export(client, creer_utilisateur):
    creer_utilisateur("Dev", "dev@test.com", "developpeur")
    connecter(client, "dev@test.com")

    r = client.get("/")
    assert "Sauvegarde recommandée" in r.data.decode()

    client.get("/sauvegarde/exporter")
    r = client.get("/")
    assert "Sauvegarde recommandée" not in r.data.decode()


def test_rappel_de_sauvegarde_invisible_sans_le_droit(client, creer_utilisateur):
    creer_utilisateur("Fond", "fond@test.com", "fondateur")
    connecter(client, "fond@test.com")
    r = client.get("/")
    assert "Sauvegarde recommandée" not in r.data.decode()
