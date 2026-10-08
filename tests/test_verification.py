"""QR code de vérification : chaque document officiel est retrouvable
sur une page publique par le code imprimé sous son QR code."""

from io import BytesIO

from tests.conftest import connecter
from tests.test_bulletins import classe_notee  # noqa: F401 (fixture)


def _texte_pdf(contenu):
    from pypdf import PdfReader
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(contenu)).pages)


def _documents():
    from app.models.document_verifiable import DocumentVerifiable
    return DocumentVerifiable.query.order_by(DocumentVerifiable.id).all()


def test_bulletin_porte_un_code_verifiable_publiquement(client, db, creer_utilisateur, classe_notee):  # noqa: F811
    creer_utilisateur("Fond", "f@t.com", "fondateur")
    connecter(client, "f@t.com")
    awa = classe_notee["awa"]

    r = client.get(f"/notes/bulletin/{awa}/pdf?trimestre=T1")
    assert r.status_code == 200
    (document,) = _documents()
    assert document.type_document == "bulletin" and document.nom_eleve == "Awa"
    assert ("Moyenne générale", "14,50 / 20") in document.details
    assert ("Maths", "16,00 / 20") in document.details
    assert document.code in _texte_pdf(r.data)

    # Réimprimé à l'identique : même code, pas de doublon.
    client.get(f"/notes/bulletin/{awa}/pdf?trimestre=T1")
    assert len(_documents()) == 1

    # Vérification par quelqu'un qui n'a pas de compte.
    client.get("/auth/deconnexion")
    page = client.get(f"/verifier/{document.code}")
    texte = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Document authentique" in texte and "École Test" in texte
    assert "Awa" in texte and "14,50 / 20" in texte
    assert page.headers["X-Robots-Tag"] == "noindex, nofollow"


def test_une_note_corrigee_donne_un_nouveau_code(client, db, creer_utilisateur, classe_notee):  # noqa: F811
    from app.models.note import Note

    creer_utilisateur("Fond", "f@t.com", "fondateur")
    connecter(client, "f@t.com")
    awa = classe_notee["awa"]
    client.get(f"/notes/bulletin/{awa}/pdf?trimestre=T1")

    note = Note.query.filter_by(eleve_id=awa, matiere="Maths", trimestre="T1").one()
    note.valeur = 18
    db.session.commit()
    client.get(f"/notes/bulletin/{awa}/pdf?trimestre=T1")

    ancien, nouveau = _documents()
    assert ancien.code != nouveau.code
    assert ("Maths", "16,00 / 20") in ancien.details and ("Maths", "18,00 / 20") in nouveau.details


def test_bulletins_de_toute_une_classe_ont_chacun_leur_code(client, creer_utilisateur, classe_notee):  # noqa: F811
    creer_utilisateur("Fond", "f@t.com", "fondateur")
    connecter(client, "f@t.com")
    r = client.get(f"/notes/classe/{classe_notee['classe']}/bulletins/pdf?trimestre=T1")
    documents = _documents()
    assert {d.nom_eleve for d in documents} == {"Awa", "Ben", "Clé"}
    texte = _texte_pdf(r.data)
    assert all(d.code in texte for d in documents)


def test_certificat_et_attestation_verifiables(client, creer_utilisateur, creer_classe, creer_eleve):
    creer_utilisateur("Secr", "secr@t.com", "secretaire")
    eleve = creer_eleve("Fatima Abakar", creer_classe(nom="CM2"), sexe="F")
    connecter(client, "secr@t.com")
    signataire = {"signataire_nom": "Mme Achta", "signataire_qualite": "Directrice", "signataire_genre": "F"}

    r = client.post(f"/documents/eleve/{eleve.id}/certificat", data=signataire)
    client.post(f"/documents/eleve/{eleve.id}/attestation", data=signataire)
    certificat, attestation = _documents()
    assert certificat.type_document == "certificat" and attestation.type_document == "attestation"
    assert certificat.reference != attestation.reference
    assert ("Signataire", "Directrice Mme Achta") in certificat.details
    assert certificat.code in _texte_pdf(r.data)

    texte = client.get(f"/verifier/{certificat.code}").get_data(as_text=True)
    assert "Certificat de scolarité" in texte and "Fatima Abakar" in texte and certificat.reference in texte


def test_recu_de_caisse_verifiable(client, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.mouvement_caisse import MouvementCaisse

    creer_utilisateur("Compt", "c@t.com", "comptable")
    eleve = creer_eleve("Eleve Test", creer_classe(frais_inscription=15000))
    connecter(client, "c@t.com")
    client.post(f"/finances/{eleve.id}", data={"echeance": "inscription", "montant": "15000", "mode": "especes"})
    mouvement = MouvementCaisse.query.one()

    r = client.get(f"/caisse/recu/{mouvement.id}/pdf")
    (document,) = _documents()
    assert document.type_document == "recu" and ("Montant", "15 000 FCFA") in document.details
    assert document.code in _texte_pdf(r.data)
    assert "15 000 FCFA" in client.get(f"/verifier/{document.code}").get_data(as_text=True)


def test_code_inconnu_ou_mal_saisi(client):
    r = client.get("/verifier/AAAA-BBBB-CCCC")
    assert r.status_code == 404 and "Aucun document ne porte ce code" in r.get_data(as_text=True)

    assert "Vérifier un document" in client.get("/verifier").get_data(as_text=True)
    r = client.post("/verifier", data={"code": "abc"}, follow_redirects=True)
    assert "pas le bon format" in r.get_data(as_text=True)
    r = client.post("/verifier", data={"code": " k7qf 3m9x-pa2d "})
    assert r.headers["Location"].endswith("/verifier/K7QF-3M9X-PA2D")


def test_document_d_une_autre_ecole_verifiable_mais_invisible_dans_l_application(app, client, db, creer_utilisateur):
    from flask import g
    from app.models.ecole import Ecole
    from app.models.document_verifiable import DocumentVerifiable
    from app.services.verification import emettre

    db.session.add(Ecole(id=2, nom="École Bêta", sigle="EB", ville="Moundou", pays="Tchad", prefixe_matricule="EB26"))
    db.session.commit()
    with app.test_request_context():
        g.ecole_id = 2
        code = emettre("recu", "recu:1", "Reçu de paiement", nom_eleve="Zara", details=[("Montant", "5 000 FCFA")]).code
        db.session.commit()

    texte = client.get(f"/verifier/{code}").get_data(as_text=True)
    assert "Document authentique" in texte and "École Bêta" in texte and "Zara" in texte

    with app.test_request_context():
        g.ecole_id = 1
        assert DocumentVerifiable.query.count() == 0


def test_normalisation_du_code():
    from app.services.verification import normaliser_code, generer_code

    assert normaliser_code("k7qf3m9xpa2d") == "K7QF-3M9X-PA2D"
    assert normaliser_code("K7QF-3M9X-PA2") is None
    assert normaliser_code("O0I1-L000-AAAA") is None  # caractères exclus car ambigus
    assert normaliser_code(None) is None


def test_code_genere_au_bon_format(app):
    from app.services.verification import generer_code, normaliser_code

    with app.test_request_context():
        code = generer_code()
    assert normaliser_code(code) == code and len(code) == 14
