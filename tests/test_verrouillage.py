"""Tests sur le verrouillage de compte (réversible, effet immédiat) et
la limitation des tentatives de connexion."""

from tests.conftest import connecter


def test_verrouiller_bloque_la_connexion(client, creer_utilisateur):
    creer_utilisateur("Dev", "dev@test.com", "developpeur")
    secr = creer_utilisateur("Secr", "secr@test.com", "secretaire")

    connecter(client, "dev@test.com")
    client.post(f"/developpeur/utilisateur/{secr.id}/verrouiller")
    client.get("/auth/deconnexion")

    r = connecter(client, "secr@test.com")
    assert "verrouillé" in r.data.decode()


def test_verrouillage_coupe_une_session_deja_ouverte(client, creer_utilisateur, db):
    creer_utilisateur("Dev", "dev@test.com", "developpeur")
    secr = creer_utilisateur("Secr", "secr@test.com", "secretaire")

    from tests.conftest import connecter as se_connecter
    from app import create_app
    from app.extensions import db as _db

    connecter(client, "secr@test.com")
    assert client.get("/").status_code == 200

    # Un verrouillage decide ailleurs (par un autre compte) doit couper
    # cette session au tour suivant, sans que secr se reconnecte.
    from app.models.user import User
    secr_frais = User.query.filter_by(email="secr@test.com").first()
    secr_frais.statut = "verrouille"
    db.session.commit()

    r = client.get("/", follow_redirects=True)
    assert "n'est plus actif" in r.data.decode() or "Connexion" in r.data.decode()


def test_impossible_de_se_verrouiller_soi_meme(client, creer_utilisateur):
    dev = creer_utilisateur("Dev", "dev@test.com", "developpeur")
    connecter(client, "dev@test.com")
    r = client.post(f"/developpeur/utilisateur/{dev.id}/verrouiller", follow_redirects=True)
    assert "propre compte" in r.data.decode()


def test_deverrouiller_permet_de_nouveau_la_connexion(client, creer_utilisateur):
    creer_utilisateur("Dev", "dev@test.com", "developpeur")
    secr = creer_utilisateur("Secr", "secr@test.com", "secretaire", statut="verrouille")

    connecter(client, "dev@test.com")
    client.post(f"/developpeur/utilisateur/{secr.id}/verrouiller")
    client.get("/auth/deconnexion")

    r = connecter(client, "secr@test.com")
    assert r.status_code == 200
    assert "verrouillé" not in r.data.decode()


def test_limite_les_tentatives_de_connexion(client, creer_utilisateur):
    creer_utilisateur("Test", "test@test.com", "secretaire", mot_de_passe="bonmotdepasse")

    statuts = []
    for _ in range(12):
        r = client.post("/auth/connexion", data={"email": "test@test.com", "mot_de_passe": "mauvais"})
        statuts.append(r.status_code)

    assert statuts.count(429) > 0, "au-delà d'un certain nombre de tentatives, ça doit être bloqué"
