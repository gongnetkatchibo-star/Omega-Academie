"""Changement de mot de passe et blocage après échecs répétés."""

from datetime import timedelta

from app.services.temps import maintenant

from tests.conftest import connecter


def _tenter(client, mot_de_passe):
    return client.post("/auth/connexion", data={"email": "u@t.com", "mot_de_passe": mot_de_passe},
                       follow_redirects=True).get_data(as_text=True)


def test_blocage_apres_cinq_echecs_puis_deblocage(client, db, creer_utilisateur):
    from app.models.user import User

    creer_utilisateur("User", "u@t.com", "parent")
    for _ in range(4):
        assert "incorrect" in _tenter(client, "faux")
    assert "incorrect" in _tenter(client, "faux")          # 5e échec : le compte se bloque
    assert "bloqué" in _tenter(client, "p12345678")        # même le bon mot de passe est refusé
    db.session.expire_all()
    user = User.query.filter_by(email="u@t.com").one()
    assert user.bloque_jusqua > maintenant()

    user.bloque_jusqua = maintenant() - timedelta(minutes=1)  # le délai est passé
    db.session.commit()
    assert "accueil-carte-ecole" in _tenter(client, "p12345678")
    db.session.expire_all()
    assert User.query.filter_by(email="u@t.com").one().bloque_jusqua is None


def test_une_reussite_remet_le_compteur_a_zero(client, db, creer_utilisateur):
    from app.models.user import User

    creer_utilisateur("User", "u@t.com", "parent")
    for _ in range(3):
        _tenter(client, "faux")
    _tenter(client, "p12345678")
    client.get("/auth/deconnexion")
    db.session.expire_all()
    assert User.query.filter_by(email="u@t.com").one().echecs_connexion == 0


def test_changer_son_mot_de_passe(client, db, creer_utilisateur):
    creer_utilisateur("User", "u@t.com", "parent")
    connecter(client, "u@t.com")
    assert "Changer le mot de passe" in client.get("/profil").get_data(as_text=True)

    def changer(actuel, nouveau, confirmation=None):
        return client.post("/profil/mot-de-passe", data={
            "mot_de_passe_actuel": actuel, "nouveau_mot_de_passe": nouveau,
            "confirmation": nouveau if confirmation is None else confirmation,
        }, follow_redirects=True).get_data(as_text=True)

    assert "actuel est incorrect" in changer("faux", "nouveau12345")
    assert "8 caractères" in changer("p12345678", "court")
    assert "ne correspondent pas" in changer("p12345678", "nouveau12345", "autre12345")
    assert "différent" in changer("p12345678", "p12345678")
    assert "Mot de passe modifié" in changer("p12345678", "nouveau12345")

    client.get("/auth/deconnexion")
    assert "incorrect" in _tenter(client, "p12345678")
    assert "accueil-carte-ecole" in _tenter(client, "nouveau12345")


def test_changement_de_mot_de_passe_reserve_au_compte_connecte(client):
    assert client.post("/profil/mot-de-passe", data={}).status_code in (302, 401)
