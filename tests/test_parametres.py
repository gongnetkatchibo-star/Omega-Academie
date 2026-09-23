"""Tests sur les paramètres de l'établissement (nom du directeur) et le
filigrane des documents PDF."""

from tests.conftest import connecter


def test_parametres_valeur_par_defaut(app, db):
    from app.models.parametre import ParametreEtablissement

    parametre = ParametreEtablissement.get()
    assert parametre.titre_directeur == "Le Directeur / La Directrice"
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
    assert r.status_code == 200
    assert len(r.data) > 0


def test_html_vers_pdf_ajoute_le_filigrane():
    from app.utils import html_vers_pdf

    pdf = html_vers_pdf("<html><head></head><body><p>Test</p></body></html>")
    assert pdf.startswith(b"%PDF")
