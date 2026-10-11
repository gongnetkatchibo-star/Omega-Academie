"""Cartes d'élève, photos des élèves, signature et cachet imprimés au
choix (oct. 2026)."""

import io

from tests.conftest import connecter


def _image(couleur=(20, 40, 160), taille=(300, 200), fmt="PNG", fond=(255, 255, 255)):
    """Un trait de couleur sur fond blanc, comme une signature photographiée."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", taille, fond)
    ImageDraw.Draw(image).line((30, 150, 270, 40), fill=couleur, width=12)
    sortie = io.BytesIO()
    image.save(sortie, fmt)
    return sortie.getvalue()


def _texte_pdf(contenu):
    from pypdf import PdfReader

    lecteur = PdfReader(io.BytesIO(contenu))
    return len(lecteur.pages), "\n".join(page.extract_text() for page in lecteur.pages)


def _images_pdf(contenu):
    from pypdf import PdfReader

    return sum(len(page.images) for page in PdfReader(io.BytesIO(contenu)).pages)


def _reglages(client, **champs):
    donnees = {"nom": "École Test", "sigle": "ET", "prefixe_matricule": "ET26", "nom_directeur": "Mme Achta Brahim",
               "titre_directeur": "Directrice", "genre_directeur": "F"}
    donnees.update(champs)
    return client.post("/developpeur/parametres", data=donnees, content_type="multipart/form-data", follow_redirects=True)


# ------------------------------------------------------------------ cartes
def test_planche_de_cartes_d_une_classe(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from datetime import date
    from app.models.document_verifiable import DocumentVerifiable

    creer_utilisateur("Sec", "s@t.td", "secretaire")
    classe = creer_classe("CM2", 5)
    for i in range(12):
        e = creer_eleve(f"Élève Numéro {i:02d}", classe, matricule=f"ET26-CM2-{i:03d}")
        e.date_naissance, e.lieu_naissance, e.nationalite = date(2014, 3, 1 + i), "Pala", "Tchadienne"
        e.personne_urgence, e.telephone_urgence = "Tante Zara", "66 00 00 00"
    db.session.commit()
    connecter(client, "s@t.td")

    page = client.get("/documents/cartes").get_data(as_text=True)
    import re; assert re.search(r"CM2 — 12 .*0 avec photo", page), page[page.find("<select"):][:600]

    r = client.post("/documents/cartes", data={"classe_id": classe.id, "verso": "on"})
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    pages, texte = _texte_pdf(r.data)
    assert pages == 4  # 12 cartes : deux feuilles recto, deux feuilles verso
    for attendu in ("CARTE D'ÉLÈVE", "ÉCOLE TEST", "Élève Numéro 11", "Né le 12/03/2014 à Pala", "Nationalité : Tchadienne",
                    "Classe : CM2", "Mat : ET26-CM2-011", "Tante Zara", "66 00 00 00", "Devise test"):
        assert attendu in texte, attendu
    # Une trace vérifiable par carte ; réimprimer ne change pas les codes.
    assert DocumentVerifiable.query.filter_by(type_document="carte").count() == 12
    codes = {d.code for d in DocumentVerifiable.query.all()}
    client.post("/documents/cartes", data={"classe_id": classe.id})
    assert {d.code for d in DocumentVerifiable.query.all()} == codes
    code = next(iter(codes))
    assert "Carte d&#39;élève" in client.get(f"/verifier/{code}").get_data(as_text=True)

    sans_verso = client.post("/documents/cartes", data={"classe_id": classe.id})
    assert _texte_pdf(sans_verso.data)[0] == 2


def test_carte_d_un_seul_eleve_avec_sa_photo(client, db, creer_utilisateur, creer_classe, creer_eleve):
    creer_utilisateur("Sec", "s@t.td", "secretaire")
    eleve = creer_eleve("Mahamat Saleh", creer_classe("6e A", 7), matricule="ET26-6A-001")
    connecter(client, "s@t.td")
    sans_photo = client.post("/documents/cartes", data={"eleve_id": eleve.id})
    assert "Coller" in _texte_pdf(sans_photo.data)[1]

    r = client.post(f"/eleves/{eleve.id}/photo", data={"photo": (io.BytesIO(_image(fmt="JPEG")), "p.jpg", "image/jpeg")},
                    content_type="multipart/form-data", headers={"X-Requested-With": "fetch"})
    assert r.get_json() == {"ok": True, "eleve_id": eleve.id}
    avec_photo = client.post("/documents/cartes", data={"eleve_id": eleve.id})
    pages, texte = _texte_pdf(avec_photo.data)
    assert pages == 1 and "Coller" not in texte and "Mahamat Saleh" in texte
    assert _images_pdf(avec_photo.data) == _images_pdf(sans_photo.data) + 1


def test_cartes_reservees_au_secretariat_et_a_la_direction_de_son_cycle(client, creer_utilisateur, creer_classe, creer_eleve):
    creer_utilisateur("Prof", "p@t.td", "enseignant")
    creer_utilisateur("Dir", "d@t.td", "directeur_primaire")
    college = creer_classe("5e", 8)
    eleve = creer_eleve("Collégien", college)
    connecter(client, "p@t.td")
    assert client.get("/documents/cartes").status_code == 403
    assert client.get("/eleves/photos").status_code == 403
    client.get("/auth/deconnexion")
    connecter(client, "d@t.td")
    assert client.get(f"/documents/cartes?eleve_id={eleve.id}").status_code == 404
    assert client.post("/documents/cartes", data={"classe_id": college.id}).status_code == 302
    assert client.post(f"/eleves/{eleve.id}/photo", data={}).status_code == 404


# ------------------------------------------------------------------ photos
def test_import_de_plusieurs_photos_par_matricule_ou_par_nom(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.eleve import Eleve

    creer_utilisateur("Sec", "s@t.td", "secretaire")
    classe = creer_classe("CE1", 2)
    a = creer_eleve("Awa Béchir", classe, matricule="ET26-CE1-001")
    b = creer_eleve("Idriss Déby", classe, matricule="ET26-CE1-002")
    creer_eleve("Jean Paul", classe, matricule="ET26-CE1-003")
    creer_eleve("Jean Paul", classe, matricule="ET26-CE1-004")
    connecter(client, "s@t.td")
    page = client.get(f"/eleves/photos?classe_id={classe.id}").get_data(as_text=True)
    assert "Awa Béchir" in page and "Pas de photo" in page

    def fichier(nom, contenu=None, mime="image/png"):
        return (io.BytesIO(contenu or _image()), nom, mime)

    r = client.post("/eleves/photos/importer", content_type="multipart/form-data", headers={"X-Requested-With": "fetch"},
                    data={"photos": [fichier("et26 ce1 001.PNG"), fichier("idriss deby.png"), fichier("Jean Paul.png"),
                                     fichier("inconnu.png"), fichier("ET26-CE1-003.png", b"pas une image")]})
    resultat = r.get_json()
    assert [x["eleve_id"] for x in resultat["rangees"]] == [a.id, b.id]
    assert [x["fichier"] for x in resultat["refusees"]] == ["Jean Paul.png", "inconnu.png", "ET26-CE1-003.png"]
    assert "matricule" in resultat["refusees"][0]["raison"]
    assert Eleve.query.filter(Eleve.photo_mime.isnot(None)).count() == 2
    assert client.get(f"/eleves/{a.id}/photo").mimetype == "image/jpeg"

    # Sans JavaScript : même envoi, compte rendu sur la page.
    r = client.post("/eleves/photos/importer", content_type="multipart/form-data", follow_redirects=True,
                    data={"classe_id": classe.id, "photos": [fichier("ET26-CE1-004.png")]})
    assert "1 photo(s) rangée(s)" in r.get_data(as_text=True)


# ------------------------------------------------------- signature et cachet
def test_signature_et_cachet_au_choix(client, app, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.ecole import Ecole
    from app.models.parametre import ParametreEtablissement

    creer_utilisateur("Fondateur", "f@t.td", "fondateur")
    creer_utilisateur("Sec", "s@t.td", "secretaire")
    eleve = creer_eleve("Fatimé Ali", creer_classe("CM1", 4), sexe="F")
    # Rien d'enregistré : pas de case à cocher, documents signés à la main.
    connecter(client, "s@t.td")
    assert 'name="signature_imprimee"' not in client.get(f"/documents/eleve/{eleve.id}/certificat").get_data(as_text=True)
    a_la_main = client.post(f"/documents/eleve/{eleve.id}/certificat", data={"signature_imprimee": "on"})
    assert client.get("/developpeur/parametres/signature").status_code == 403
    client.get("/auth/deconnexion")

    connecter(client, "f@t.td")
    assert client.get("/developpeur/parametres/signature").status_code == 404
    r = _reglages(client, signature=(io.BytesIO(_image(fmt="JPEG")), "signature.jpg", "image/jpeg"),
                  cachet=(io.BytesIO(_image((170, 30, 30))), "cachet.png", "image/png"))
    assert "Paramètres enregistrés" in r.get_data(as_text=True)
    ecole = db.session.get(Ecole, 1)
    from PIL import Image
    nettoyee = Image.open(io.BytesIO(ecole.signature))
    assert nettoyee.mode == "RGBA" and nettoyee.getpixel((0, 0))[3] == 0  # le papier blanc a disparu
    assert max(p[3] for p in nettoyee.getdata()) == 255                   # l'encre est restée
    assert client.get("/developpeur/parametres/cachet").mimetype == "image/png"
    assert not ParametreEtablissement.get().signature_imprimee
    client.get("/auth/deconnexion")

    # Réglage de l'école : à la main. Le choix est proposé document par document.
    connecter(client, "s@t.td")
    assert 'name="signature_imprimee"' in client.get(f"/documents/eleve/{eleve.id}/certificat").get_data(as_text=True)
    manuscrit = client.post(f"/documents/eleve/{eleve.id}/certificat", data={})
    imprime = client.post(f"/documents/eleve/{eleve.id}/certificat", data={"signature_imprimee": "on"})
    assert _images_pdf(manuscrit.data) == _images_pdf(a_la_main.data)
    assert _images_pdf(imprime.data) == _images_pdf(manuscrit.data) + 1
    # La signature enregistrée ne s'imprime jamais sous un autre nom.
    autre = client.post(f"/documents/eleve/{eleve.id}/certificat",
                        data={"signature_imprimee": "on", "signataire_nom": "Quelqu'un d'autre"})
    assert _images_pdf(autre.data) == _images_pdf(manuscrit.data)

    carte_main = client.post("/documents/cartes", data={"eleve_id": eleve.id})
    carte_signee = client.post("/documents/cartes", data={"eleve_id": eleve.id, "signature_imprimee": "on"})
    assert _images_pdf(carte_signee.data) == _images_pdf(carte_main.data) + 1
    assert "La Directrice" in _texte_pdf(carte_signee.data)[1] and "Mme Achta Brahim" in _texte_pdf(carte_signee.data)[1]
    client.get("/auth/deconnexion")

    # Réglage de l'école : imprimés. Bulletins, reçus et fiches de paie suivent le réglage.
    from flask import g
    from app.services.documents_officiels import contexte_entete_officiel

    def signature_des_documents():
        db.session.expire_all()
        with app.test_request_context():
            g.ecole_id = 1
            return contexte_entete_officiel()["signature_uri"]

    assert signature_des_documents() is None
    connecter(client, "f@t.td")
    _reglages(client, signature_imprimee="on")
    assert signature_des_documents().startswith("data:image/png;base64,")
    _reglages(client, signature_imprimee="on", retirer_signature="on", retirer_cachet="on")
    assert signature_des_documents() is None
    assert db.session.get(Ecole, 1).signature is None and db.session.get(Ecole, 1).cachet is None
