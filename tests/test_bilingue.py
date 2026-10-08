"""Bilingue français / arabe : choix de la langue de l'interface et
documents officiels en deux langues."""

from tests.conftest import connecter


def test_choisir_l_arabe_passe_l_interface_de_droite_a_gauche(client, db, creer_utilisateur):
    from app.models.user import User

    creer_utilisateur("Amina Mahamat", "f@t.com", "fondateur")
    connecter(client, "f@t.com")
    assert 'dir="ltr"' in client.get("/").get_data(as_text=True)

    r = client.get("/langue/ar", headers={"Referer": "http://localhost/eleves/"})
    assert r.headers["Location"].endswith("/eleves/")
    page = client.get("/").get_data(as_text=True)
    assert 'lang="ar" dir="rtl"' in page
    assert "لوحة القيادة" in page and "مرحبًا، Amina" in page and "التلاميذ المسجلون" in page
    assert User.query.filter_by(email="f@t.com").one().langue == "ar"

    client.get("/langue/fr")
    assert "Bonjour, Amina" in client.get("/").get_data(as_text=True)


def test_la_langue_est_retenue_sur_le_compte(client, db, creer_utilisateur):
    utilisateur = creer_utilisateur("Secr", "s@t.com", "secretaire")
    utilisateur.langue = "ar"
    db.session.commit()
    connecter(client, "s@t.com")
    assert 'dir="rtl"' in client.get("/").get_data(as_text=True)


def test_page_publique_en_arabe_sans_compte(client):
    client.get("/langue/ar")
    page = client.get("/").get_data(as_text=True)
    assert "إنشاء حساب" in page and "تحققوا من صحته" in page


def test_retour_jamais_vers_un_autre_site(client):
    r = client.get("/langue/ar", headers={"Referer": "https://exemple-malveillant.com/page"})
    assert r.headers["Location"].endswith("/")
    assert client.get("/langue/xx").status_code == 404


def test_traduction_absente_reste_en_francais_et_valeurs_echappees(app):
    from flask import request
    from app.services.langues import traduire

    with app.test_request_context():
        request.environ["toumai.langue"] = "ar"
        assert traduire("Un texte pas encore traduit") == "Un texte pas encore traduit"
        assert traduire("Tableau de bord") == "لوحة القيادة"
        assert "&lt;script&gt;" in traduire("Bonjour, {prenom}", prenom="<script>")
        assert traduire("Recouvrement de l'année") == "نسبة التحصيل السنوية"
    with app.test_request_context():
        request.environ["toumai.langue"] = "fr"
        assert traduire("Recouvrement de l'année") == "Recouvrement de l'année"


def test_montants_isoles_en_arabe_seulement(app):
    from flask import request

    fcfa = app.jinja_env.filters["fcfa"]
    with app.test_request_context():
        request.environ["toumai.langue"] = "ar"
        assert fcfa(145000) == "⁦145 000 FCFA⁩"
    with app.test_request_context():
        request.environ["toumai.langue"] = "fr"
        assert fcfa(145000) == "145 000 FCFA"


def test_arabe_pdf_garde_les_noms_et_numeros_dans_le_bon_ordre():
    from app.services.langues import arabe_pdf

    texte = arabe_pdf("القسم : ⟦6e A⟧")
    # Lu de droite à gauche : « القسم : » à droite, « 6e A » à gauche, intact.
    assert texte.startswith("6e A")
    assert any("ﹰ" <= c <= "﻿" for c in texte)  # lettres liées (formes de présentation)
    assert arabe_pdf("السنة الدراسية ⟦2026-2027⟧").startswith("2026-2027")
    assert arabe_pdf("") == ""


def _activer_documents_bilingues(client):
    client.post("/developpeur/parametres", data={
        "nom": "École Test", "sigle": "ET", "prefixe_matricule": "ET26", "ville": "Pala", "pays": "Tchad",
        "nom_arabe": "مدرسة الاختبار", "ville_arabe": "بالا", "documents_bilingues": "on",
    })


def test_parametres_enregistrent_le_nom_arabe(client, db, creer_utilisateur):
    from app.models.ecole import Ecole
    from app.models.parametre import ParametreEtablissement

    creer_utilisateur("Fond", "f@t.com", "fondateur")
    connecter(client, "f@t.com")
    _activer_documents_bilingues(client)
    db.session.expire_all()
    assert db.session.get(Ecole, 1).nom_arabe == "مدرسة الاختبار"
    assert ParametreEtablissement.get().documents_bilingues is True
    assert 'value="مدرسة الاختبار"' in client.get("/developpeur/parametres").get_data(as_text=True)


def test_certificat_bilingue_embarque_la_police_arabe(client, creer_utilisateur, creer_classe, creer_eleve):
    creer_utilisateur("Fond", "f@t.com", "fondateur")
    eleve = creer_eleve("Fatima Abakar", creer_classe(nom="CM2"), sexe="F")
    connecter(client, "f@t.com")
    signataire = {"signataire_nom": "M. X", "signataire_qualite": "Directeur", "signataire_genre": "M"}

    unilingue = client.post(f"/documents/eleve/{eleve.id}/certificat", data=signataire)
    assert unilingue.status_code == 200 and b"NotoNaskhArabic" not in unilingue.data

    _activer_documents_bilingues(client)
    for type_doc in ("certificat", "attestation"):
        r = client.post(f"/documents/eleve/{eleve.id}/{type_doc}", data=signataire)
        assert r.status_code == 200 and r.headers["Content-Type"] == "application/pdf"
        assert b"NotoNaskhArabic" in r.data, type_doc


def test_bulletin_et_recu_bilingues(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.note import Note
    from app.models.mouvement_caisse import MouvementCaisse

    creer_utilisateur("Fond", "f@t.com", "fondateur")
    classe = creer_classe(nom="6e", niveau=7, frais_inscription=15000)
    eleve = creer_eleve("Awa", classe, matricule="ET26-6E-001")
    db.session.add(Note(eleve_id=eleve.id, classe_id=classe.id, matiere="Mathématiques", valeur=15, bareme=20,
                        trimestre="T1", annee_scolaire=classe.annee_scolaire))
    db.session.commit()
    connecter(client, "f@t.com")
    _activer_documents_bilingues(client)

    r = client.get(f"/notes/bulletin/{eleve.id}/pdf?trimestre=T1")
    assert r.status_code == 200 and b"NotoNaskhArabic" in r.data

    client.post(f"/finances/{eleve.id}", data={"echeance": "inscription", "montant": "15000", "mode": "especes"})
    r = client.get(f"/caisse/recu/{MouvementCaisse.query.one().id}/pdf")
    assert r.status_code == 200 and b"NotoNaskhArabic" in r.data
