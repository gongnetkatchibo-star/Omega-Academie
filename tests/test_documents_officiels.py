"""Tests sur les documents officiels — date automatique, numérotation
séquentielle sans doublon, génération du certificat et de l'attestation."""

from datetime import date

from tests.conftest import connecter


def test_date_officielle_format_1er():
    from app.services.documents_officiels import date_officielle

    assert date_officielle(date(2026, 6, 1)) == "1er juin 2026"
    assert date_officielle(date(2026, 9, 20)) == "20 septembre 2026"


def test_numerotation_incremente_et_separe_par_type(app, db):
    from app.services.documents_officiels import numero_reference

    assert numero_reference("CERT", annee=2026) == "001/CSOA/CERT/2026"
    assert numero_reference("CERT", annee=2026) == "002/CSOA/CERT/2026"
    assert numero_reference("ATTEST", annee=2026) == "001/CSOA/ATTEST/2026"


def test_certificat_scolarite_genere_un_pdf(client, creer_utilisateur, creer_classe, creer_eleve):
    creer_utilisateur("Secr", "secr@test.com", "secretaire")
    classe = creer_classe(nom="CM2")
    eleve = creer_eleve("Fatima Abakar", classe)

    connecter(client, "secr@test.com")
    r = client.get(f"/documents/eleve/{eleve.id}/certificat")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/pdf"


def test_attestation_frequentation_genere_un_pdf(client, creer_utilisateur, creer_classe, creer_eleve):
    creer_utilisateur("Secr", "secr@test.com", "secretaire")
    classe = creer_classe(nom="CM2")
    eleve = creer_eleve("Moussa Idriss", classe)

    connecter(client, "secr@test.com")
    r = client.get(f"/documents/eleve/{eleve.id}/attestation")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/pdf"


def test_enseignant_ne_peut_pas_generer_de_document_officiel(client, creer_utilisateur, creer_classe, creer_eleve):
    creer_utilisateur("Prof", "prof@test.com", "enseignant")
    classe = creer_classe()
    eleve = creer_eleve("Eleve Test", classe)

    connecter(client, "prof@test.com")
    r = client.get(f"/documents/eleve/{eleve.id}/certificat")
    assert r.status_code == 403
