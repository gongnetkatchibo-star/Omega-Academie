"""Tests sur les paramètres de l'établissement (nom du directeur) et le
filigrane des documents PDF."""

from tests.conftest import connecter


def test_parametres_valeur_par_defaut(app, db):
    from app.models.parametre import ParametreEtablissement

    parametre = ParametreEtablissement.get()
    assert parametre.titre_directeur == "Directeur"
    assert parametre.nom_directeur is None


def test_configurer_nom_directeur(client, creer_utilisateur):
    creer_utilisateur("Dev", "dev@test.com", "developpeur")
    connecter(client, "dev@test.com")

    client.post("/developpeur/parametres", data={
        "nom_directeur": "M. ABAKAR IDRISS", "titre_directeur": "Le Directeur Général",
    })

    from app.models.parametre import ParametreEtablissement
    parametre = ParametreEtablissement.get()
    assert parametre.nom_directeur == "M. ABAKAR IDRISS"
    assert parametre.titre_directeur == "Le Directeur Général"


def test_certificat_utilise_le_nom_du_directeur_configure(client, creer_utilisateur, creer_classe, creer_eleve):
    creer_utilisateur("Dev", "dev@test.com", "developpeur")
    classe = creer_classe()
    eleve = creer_eleve("Fatima Abakar", classe)
    connecter(client, "dev@test.com")

    client.post("/developpeur/parametres", data={"nom_directeur": "M. ABAKAR IDRISS", "titre_directeur": "Le Directeur Général"})

    r = client.get(f"/documents/eleve/{eleve.id}/certificat")
    assert "M. ABAKAR IDRISS" in r.data.decode()


def test_html_vers_pdf_ajoute_le_filigrane():
    from app.utils import html_vers_pdf

    pdf = html_vers_pdf("<html><head></head><body><p>Test</p></body></html>")
    assert pdf.startswith(b"%PDF")


def test_genre_modifiable_depuis_le_profil(client, creer_utilisateur):
    from app.models.user import User

    creer_utilisateur("Prof", "prof@test.com", "enseignant")
    connecter(client, "prof@test.com")
    client.post("/profil/genre", data={"genre": "F"})
    assert User.query.filter_by(email="prof@test.com").first().genre == "F"


def test_genre_affiche_sur_la_fiche_eleve(client, creer_utilisateur, creer_classe, creer_eleve):
    creer_utilisateur("Secr", "secr@test.com", "secretaire")
    classe = creer_classe()
    eleve = creer_eleve("Awa", classe)
    eleve.sexe = "F"
    from app.extensions import db as _db
    _db.session.commit()
    connecter(client, "secr@test.com")
    assert "Féminin" in client.get(f"/eleves/{eleve.id}").data.decode()


def test_filigrane_a_la_position_du_document_de_reference():
    from app.utils import html_vers_pdf
    import re

    capture = {}
    import xhtml2pdf.pisa as pisa
    original = pisa.CreatePDF

    def espion(src, dest, encoding):
        capture["html"] = src
        return original(src=src, dest=dest, encoding=encoding)

    pisa.CreatePDF = espion
    try:
        html_vers_pdf("<html><head></head><body>x</body></html>")
    finally:
        pisa.CreatePDF = original
    assert "background-object-position: 71pt 211pt" in capture["html"]
    assert "background-width: 453pt" in capture["html"]
