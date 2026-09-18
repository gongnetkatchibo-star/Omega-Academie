"""Tests sur la validation des numéros tchadiens et leur gestion."""

from tests.conftest import connecter


def test_normalisation_numero_tchad():
    from app.utils import normaliser_numero_tchad

    assert normaliser_numero_tchad("66123456") == "+23566123456"
    assert normaliser_numero_tchad("90 12 34 56") == "+23590123456"
    assert normaliser_numero_tchad("+235 66 12 34 56") == "+23566123456"
    assert normaliser_numero_tchad("22 51 12 34") is None  # ligne fixe
    assert normaliser_numero_tchad("123") is None  # trop court
    assert normaliser_numero_tchad("88123456") is None  # prefixe invalide


def test_ajout_numero_telephone(client, creer_utilisateur):
    from app.models.telephone import NumeroTelephone

    creer_utilisateur("Parent", "parent@test.com", "parent")
    connecter(client, "parent@test.com")

    client.post("/profil/numero/ajouter", data={"numero": "66123456", "operateur": "airtel", "libelle": "Principal"})
    numero = NumeroTelephone.query.first()
    assert numero.numero == "+23566123456"
    assert numero.operateur == "airtel"


def test_numero_invalide_refuse(client, creer_utilisateur):
    from app.models.telephone import NumeroTelephone

    creer_utilisateur("Parent", "parent@test.com", "parent")
    connecter(client, "parent@test.com")

    client.post("/profil/numero/ajouter", data={"numero": "123", "operateur": "airtel"})
    assert NumeroTelephone.query.count() == 0


def test_impossible_de_supprimer_le_numero_dun_autre(client, creer_utilisateur, db):
    from app.models.telephone import NumeroTelephone

    p1 = creer_utilisateur("Parent Un", "p1@test.com", "parent")
    creer_utilisateur("Parent Deux", "p2@test.com", "parent")

    numero = NumeroTelephone(user_id=p1.id, numero="+23566123456", operateur="airtel")
    db.session.add(numero)
    db.session.commit()

    connecter(client, "p2@test.com")
    r = client.post(f"/profil/numero/{numero.id}/supprimer")
    assert r.status_code == 403
    assert NumeroTelephone.query.count() == 1
