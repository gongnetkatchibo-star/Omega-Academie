"""Application installable et lecture hors ligne."""

from tests.conftest import connecter


def test_manifeste_et_service_worker(client):
    manifeste = client.get("/manifest.webmanifest")
    assert manifeste.status_code == 200 and manifeste.mimetype == "application/manifest+json"
    donnees = manifeste.get_json()
    assert donnees["display"] == "standalone" and donnees["theme_color"] == "#0F5FA6"
    for icone in donnees["icons"]:
        assert client.get(icone["src"]).status_code == 200

    sw = client.get("/sw.js")
    assert sw.status_code == 200 and sw.mimetype == "text/javascript"
    assert sw.headers["Service-Worker-Allowed"] == "/" and sw.headers["Cache-Control"] == "no-cache"
    code = sw.get_data(as_text=True)
    assert '"/hors-ligne"' in code and "/static/css/style.css?v=" in code
    # Fichiers préchargés : tous doivent exister, sinon l'installation échoue.
    import json, re
    for adresse in json.loads(re.search(r"const A_PRECHARGER = (\[.*?\]);", code).group(1)):
        assert client.get(adresse).status_code == 200, adresse


def test_page_hors_ligne_publique_et_sans_donnees_de_compte(client, creer_utilisateur):
    creer_utilisateur("Amina Mahamat", "f@t.com", "fondateur")
    connecter(client, "f@t.com")
    page = client.get("/hors-ligne").get_data(as_text=True)
    assert "Pas de connexion" in page and "لا يوجد اتصال" in page
    assert "Amina" not in page  # elle reste en mémoire après la déconnexion


def test_pages_annoncent_l_application(client, creer_utilisateur):
    page_publique = client.get("/auth/connexion").get_data(as_text=True)
    assert 'rel="manifest"' in page_publique and 'data-connecte="non"' in page_publique
    assert "js/application.js" in page_publique

    creer_utilisateur("Amina Mahamat", "f@t.com", "fondateur")
    connecter(client, "f@t.com")
    page = client.get("/").get_data(as_text=True)
    assert 'data-connecte="oui"' in page and 'id="bouton-installer"' in page
    assert 'id="bandeau-hors-ligne"' in page


def _logo_png(largeur=300, hauteur=120):
    import io
    from PIL import Image
    tampon = io.BytesIO()
    Image.new("RGBA", (largeur, hauteur), "#0F5FA6").save(tampon, "PNG")
    return tampon.getvalue()


def test_l_application_installee_porte_le_nom_et_le_logo_de_l_ecole(client, db, creer_utilisateur):
    """Chaque école a sa fiche d'application : son nom, sa couleur et une
    icône carrée tirée de son logo, sans le déformer."""
    import io
    from PIL import Image
    from app.models.ecole import Ecole

    ecole = db.session.get(Ecole, 1)
    ecole.identifiant, ecole.logo, ecole.logo_mime, ecole.couleur_theme = "ecole-test", _logo_png(), "image/png", "#7A1F3D"
    db.session.commit()

    # Visiteur arrivé par le lien de l'école, puis compte connecté : même fiche.
    page = client.get("/e/ecole-test").get_data(as_text=True)
    assert 'href="/e/ecole-test/manifest.webmanifest"' in page and "/e/ecole-test/icone-180.png" in page
    creer_utilisateur("Amina Mahamat", "f@t.com", "fondateur")
    connecter(client, "f@t.com")
    page = client.get("/").get_data(as_text=True)
    assert 'href="/e/ecole-test/manifest.webmanifest"' in page and "barre-devise-logo" in page
    client.get("/auth/deconnexion")

    donnees = client.get("/e/ecole-test/manifest.webmanifest").get_json()  # lu sans cookie par le navigateur
    assert donnees["name"] == "École Test" and donnees["short_name"] == "ET"
    assert donnees["theme_color"] == "#7A1F3D" and donnees["start_url"].startswith("/e/ecole-test")
    assert [i["sizes"] for i in donnees["icons"]] == ["192x192", "512x512", "512x512"]
    for icone in donnees["icons"]:
        reponse = client.get(icone["src"])
        assert reponse.status_code == 200 and reponse.mimetype == "image/png"
        image = Image.open(io.BytesIO(reponse.data))
        cote = int(icone["sizes"].split("x")[0])
        assert image.size == (cote, cote)
        assert image.getpixel((2, 2))[:3] == (255, 255, 255)            # marge blanche
        assert image.getpixel((cote // 2, cote // 2))[:3] == (15, 95, 166)  # le logo, au centre

    assert client.get("/e/ecole-test/icone-999.png").status_code == 404


def test_ecole_sans_logo_garde_l_icone_de_la_plateforme(client, db):
    from app.models.ecole import Ecole

    ecole = db.session.get(Ecole, 1)
    ecole.identifiant = "ecole-test"
    db.session.commit()
    donnees = client.get("/e/ecole-test/manifest.webmanifest").get_json()
    assert donnees["name"] == "École Test"
    assert all("/static/images/application/" in i["src"] for i in donnees["icons"])
    assert client.get("/e/ecole-test/icone-192.png").status_code == 404
    assert client.get("/e/inconnue/manifest.webmanifest").status_code == 404
