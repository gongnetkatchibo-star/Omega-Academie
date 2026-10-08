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
