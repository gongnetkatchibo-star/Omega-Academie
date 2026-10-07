"""Dossier élève complet : champs, photo, modification."""

import io

from PIL import Image

from tests.conftest import connecter


def _photo(taille=(1200, 1600), forme="JPEG"):
    tampon = io.BytesIO()
    Image.new("RGB", taille, (30, 90, 160)).save(tampon, forme)
    tampon.seek(0)
    return tampon


def test_inscription_avec_dossier_complet_et_photo(client, db, creer_utilisateur, creer_classe):
    from app.models.eleve import Eleve

    creer_utilisateur("Sec", "s@t.com", "secretaire")
    classe = creer_classe(nom="CE1", niveau=3)
    connecter(client, "s@t.com")
    r = client.post("/eleves/nouveau", data={
        "nom_complet": "Awa Mahamat", "classe_id": classe.id, "sexe": "F", "date_naissance": "2017-03-04",
        "lieu_naissance": "Pala", "nationalite": "Tchadienne", "adresse": "Quartier Zalbi",
        "nom_pere": "Mahamat Ali", "nom_mere": "Achta Brahim", "telephone_parent": "+23566112233",
        "personne_urgence": "Oncle Hassan", "telephone_urgence": "+23599001122", "ecole_origine": "École du Centre",
        "photo": (_photo(), "awa.jpg"),
    }, content_type="multipart/form-data", follow_redirects=True)
    page = r.get_data(as_text=True)
    db.session.expire_all()
    eleve = Eleve.query.one()
    assert (eleve.lieu_naissance, eleve.nationalite, eleve.nom_mere) == ("Pala", "Tchadienne", "Achta Brahim")
    assert eleve.telephone_parent == "+23566112233" and eleve.ecole_origine == "École du Centre"
    assert "à Pala" in page and "Oncle Hassan" in page and f"/eleves/{eleve.id}/photo" in page

    # La photo est réduite et convertie, jamais stockée telle quelle.
    image = Image.open(io.BytesIO(eleve.photo))
    assert max(image.size) == 400 and eleve.photo_mime == "image/jpeg" and len(eleve.photo) < 60_000
    r = client.get(f"/eleves/{eleve.id}/photo")
    assert r.status_code == 200 and r.headers["Content-Type"] == "image/jpeg"


def test_modifier_le_dossier(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.eleve import Eleve

    creer_utilisateur("Sec", "s@t.com", "secretaire")
    eleve = creer_eleve("Ancien Nom", creer_classe())
    eid = eleve.id
    connecter(client, "s@t.com")
    assert "Modifier le dossier" in client.get(f"/eleves/{eid}").get_data(as_text=True)
    r = client.post(f"/eleves/{eid}/modifier", data={
        "nom_complet": "Nouveau Nom", "sexe": "M", "date_naissance": "2016-01-02", "nationalite": "Tchadienne",
        "photo": (_photo(forme="PNG"), "p.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert "Dossier mis à jour" in r.get_data(as_text=True)
    db.session.expire_all()
    eleve = db.session.get(Eleve, eid)
    assert eleve.nom_complet == "Nouveau Nom" and str(eleve.date_naissance) == "2016-01-02" and eleve.photo

    client.post(f"/eleves/{eid}/modifier", data={"nom_complet": "Nouveau Nom", "retirer_photo": "on"},
                content_type="multipart/form-data")
    db.session.expire_all()
    assert db.session.get(Eleve, eid).photo is None
    assert client.get(f"/eleves/{eid}/photo").status_code == 404


def test_fichier_qui_n_est_pas_une_image_refuse(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.eleve import Eleve

    creer_utilisateur("Sec", "s@t.com", "secretaire")
    eid = creer_eleve("Élève", creer_classe()).id
    connecter(client, "s@t.com")
    r = client.post(f"/eleves/{eid}/modifier", data={
        "nom_complet": "Nom Changé", "photo": (io.BytesIO(b"pas une image"), "faux.jpg", "image/jpeg"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert "pas une image valide" in r.get_data(as_text=True)
    db.session.expire_all()
    assert db.session.get(Eleve, eid).nom_complet == "Élève"  # rien n'est enregistré


def test_modification_et_photo_protegees(client, db, creer_utilisateur, creer_classe, creer_eleve):
    creer_utilisateur("Parent", "p@t.com", "parent")
    eleve = creer_eleve("Élève", creer_classe())
    eleve.photo, eleve.photo_mime = b"x", "image/jpeg"
    db.session.commit()
    connecter(client, "p@t.com")
    assert client.get(f"/eleves/{eleve.id}/modifier").status_code == 403
    assert client.get(f"/eleves/{eleve.id}/photo").status_code == 404  # pas son enfant
