"""Corrections de l'audit de sécurité (oct. 2026) : prise de compte par le
lien « mot de passe oublié », fichiers piégés, formules dans les exports,
valeurs démesurées, droits d'accès."""

import io
import zipfile

from tests.conftest import connecter


def _texte(r):
    return r.get_data(as_text=True)


# --------------------------------------------------------------- mot de passe oublié
def test_lien_de_reinitialisation_jamais_affiche_en_production(app, client, creer_utilisateur):
    app.config["AFFICHER_SECRETS_SANS_EMAIL"] = False  # comme en production, email en panne
    creer_utilisateur("Victime", "victime@t.td", "parent")
    page = _texte(client.post("/auth/mot-de-passe-oublie", data={"email": "victime@t.td"}))
    assert "/auth/reinitialiser/" not in page
    assert "Si un compte existe" in page


def test_lien_de_reinitialisation_a_usage_unique(app, client, db, creer_utilisateur):
    from app.auth.routes import generer_token_reset

    user = creer_utilisateur("Awa", "awa@t.td", "parent")
    with app.test_request_context():
        jeton = generer_token_reset(user)
    r = client.post(f"/auth/reinitialiser/{jeton}", data={"mot_de_passe": "nouveau12345", "confirmation": "nouveau12345"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/auth/connexion")
    # Le même lien ne sert plus une fois le mot de passe changé.
    r = client.post(f"/auth/reinitialiser/{jeton}", data={"mot_de_passe": "pirate12345", "confirmation": "pirate12345"},
                    follow_redirects=True)
    assert "invalide ou a expiré" in _texte(r)
    db.session.expire_all()
    assert user.verifier_mot_de_passe("nouveau12345")


def test_code_de_verification_jamais_affiche_en_production(app, client):
    app.config["AFFICHER_SECRETS_SANS_EMAIL"] = False
    r = client.post("/auth/inscription", data={
        "role": "enseignant", "nom_complet": "Prof Test", "email": "prof@t.td", "genre": "M", "ecole_id": "1",
        "mot_de_passe": "solide12345", "confirmation": "solide12345",
    }, follow_redirects=True)
    assert "code de vérification :" not in _texte(r)
    assert "pas pu partir" in _texte(r)


def test_mot_de_passe_trop_court_refuse_a_l_inscription(client):
    from app.models.user import User

    r = client.post("/auth/inscription", data={
        "role": "enseignant", "nom_complet": "Prof Test", "email": "prof@t.td", "genre": "M", "ecole_id": "1",
        "mot_de_passe": "1234", "confirmation": "1234",
    }, follow_redirects=True)
    assert "8 caractères" in _texte(r)
    assert User.query.filter_by(email="prof@t.td").count() == 0


def test_pas_de_redirection_vers_un_autre_site_apres_connexion(client, creer_utilisateur):
    creer_utilisateur("Awa", "awa@t.td", "parent")
    r = client.post("/auth/connexion?next=/\\evil.example", data={"email": "awa@t.td", "mot_de_passe": "p12345678"})
    assert r.status_code == 302 and "evil" not in r.headers["Location"]


# ------------------------------------------------------------------ comptes
def test_le_secretariat_ne_rouvre_pas_un_compte_verrouille(client, db, creer_utilisateur):
    creer_utilisateur("Secrétaire", "sec@t.td", "secretaire")
    bloque = creer_utilisateur("Bloqué", "bloque@t.td", "parent", statut="verrouille")
    connecter(client, "sec@t.td")
    client.post(f"/secretariat/demandes/{bloque.id}/approuver")
    db.session.expire_all()
    assert bloque.statut == "verrouille"


# ------------------------------------------------------------------ fichiers
def test_fichier_html_deguise_en_image_n_est_jamais_servi_comme_page(client, db, creer_utilisateur):
    from app.models.ressource import Ressource

    creer_utilisateur("Prof", "prof@t.td", "enseignant")
    connecter(client, "prof@t.td")
    piege = (io.BytesIO(b"<script>alert(1)</script>"), "photo.png", "text/html")
    client.post("/bibliotheque/nouvelle", data={"titre": "Piège", "type": "cours", "fichier": piege,
                                                 "consultation_sur_place": "on"},
                content_type="multipart/form-data")
    ressource = Ressource.query.one()
    assert ressource.type_mime == "image/png"
    r = client.get(f"/bibliotheque/{ressource.id}/telecharger")
    assert r.mimetype == "image/png" and "sandbox" in r.headers["Content-Security-Policy"]


def test_nom_de_fichier_sans_lettre_latine_garde_son_extension():
    from app.utils import nom_fichier_sur
    assert nom_fichier_sur("دروس.pdf") == "fichier.pdf"
    assert nom_fichier_sur("Cours de maths.docx") == "Cours_de_maths.docx"


# ------------------------------------------------------------------ exports
def test_export_ne_transporte_pas_de_formule(app):
    import openpyxl
    from app.utils import export_csv, export_xlsx

    lignes = [("=HYPERLINK(\"http://x\")", 12, "+235 66 12 34 56"), ("Awa", -3, "normal")]
    with app.test_request_context():
        csv_texte = export_csv(["Nom", "Note", "Tel"], lignes, "essai").get_data().decode("utf-8-sig")
        xlsx = export_xlsx(["Nom", "Note", "Tel"], lignes, "essai").get_data()
    assert "'=HYPERLINK" in csv_texte and ";-3;" in csv_texte
    feuille = openpyxl.load_workbook(io.BytesIO(xlsx)).active
    assert feuille["A2"].data_type == "s" and feuille["A2"].value.startswith("=HYPERLINK")
    assert feuille["B3"].value == -3


# -------------------------------------------------------- valeurs démesurées
def test_identifiant_demesure_donne_400_et_pas_500(client, creer_utilisateur):
    creer_utilisateur("Secrétaire", "sec@t.td", "secretaire")
    connecter(client, "sec@t.td")
    r = client.post("/eleves/nouveau", data={"nom_complet": "X", "classe_id": "99999999999999999999"})
    # SQLite refuse le nombre (400) ; PostgreSQL ne trouve simplement pas
    # la classe (message dans la page). Dans les deux cas : pas d'erreur 500.
    assert r.status_code in (200, 400)
    assert "invalide" in _texte(r) or "introuvable" in _texte(r)


def test_page_expiree_explique_au_lieu_d_une_erreur_brute(app, client, creer_utilisateur):
    app.config["WTF_CSRF_ENABLED"] = True
    r = client.post("/auth/connexion", data={"email": "x@t.td", "mot_de_passe": "x"})
    assert r.status_code == 400 and "expiré" in _texte(r)


# ------------------------------------------------------------------ droits
def test_enseignant_ne_voit_que_les_bulletins_de_ses_classes(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.enseignant import Enseignant, Affectation

    prof = creer_utilisateur("Prof", "prof@t.td", "enseignant")
    sa_classe, autre = creer_classe(nom="6e", niveau=7), creer_classe(nom="5e", niveau=8)
    profil = Enseignant(user_id=prof.id)
    db.session.add(profil)
    db.session.commit()
    db.session.add(Affectation(enseignant_id=profil.id, classe_id=sa_classe.id, matiere="Maths"))
    db.session.commit()
    eleve_a_lui = creer_eleve("Awa", sa_classe, matricule="M1")
    eleve_autre = creer_eleve("Ben", autre, matricule="M2")
    connecter(client, "prof@t.td")
    assert client.get(f"/notes/bulletin/{eleve_a_lui.id}").status_code == 200
    assert client.get(f"/notes/bulletin/{eleve_autre.id}").status_code == 403


def test_directeur_de_cycle_ne_voit_pas_les_dossiers_de_l_autre_cycle(client, creer_utilisateur, creer_classe, creer_eleve):
    creer_utilisateur("Dir collège", "dco@t.td", "directeur_college")
    primaire = creer_eleve("Awa", creer_classe(nom="CP1", niveau=1), matricule="M1")
    college = creer_eleve("Ben", creer_classe(nom="6e", niveau=7), matricule="M2")
    connecter(client, "dco@t.td")
    assert client.get(f"/eleves/{college.id}").status_code == 200
    assert client.get(f"/eleves/{primaire.id}").status_code == 403


def test_finances_d_un_eleve_respectent_la_matrice_des_permissions(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.permission import Permission

    creer_utilisateur("Compta", "compta@t.td", "comptable")
    eleve = creer_eleve("Awa", creer_classe(frais_inscription=10000))
    db.session.add(Permission(role="comptable", module="finances", autorise=False))
    db.session.commit()
    connecter(client, "compta@t.td")
    assert client.get(f"/finances/{eleve.id}").status_code == 403


# ------------------------------------------------------------------ surveillance
def test_point_de_sante_pour_la_surveillance(client):
    r = client.get("/sante")
    assert r.status_code == 200 and r.get_json() == {"etat": "ok"}
