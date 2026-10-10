"""Réglages par école (oct. 2026) : permissions propres à chaque école,
code par email à la connexion de la direction, couleurs de l'interface,
fiche de paie."""

import re

import pytest

from tests.conftest import connecter


def _texte(r):
    return r.get_data(as_text=True)


@pytest.fixture
def deux_ecoles(db):
    from app.models.ecole import Ecole
    db.session.add(Ecole(id=2, nom="École Deux", sigle="E2", prefixe_matricule="E226"))
    db.session.commit()


# ---------------------------------------------------------------- permissions
def test_permission_propre_a_une_ecole_ne_touche_pas_l_autre(client, db, deux_ecoles, creer_utilisateur):
    creer_utilisateur("Fondateur 1", "f1@t.td", "fondateur")
    creer_utilisateur("Sec 1", "s1@t.td", "secretaire")
    creer_utilisateur("Sec 2", "s2@t.td", "secretaire", ecole_id=2)

    connecter(client, "f1@t.td")
    assert client.get("/developpeur/permissions").status_code == 200
    # Le fondateur ouvre les finances au secrétariat de SON école.
    from app.models.permission import MODULES
    from app.services.modules_par_defaut import ROLES_PAR_DEFAUT
    from app.models.user import ROLES
    cases = {f"{r}__{m}": "on" for r in ROLES if r != "developpeur" for m, _ in MODULES if r in ROLES_PAR_DEFAUT.get(m, [])}
    cases["secretaire__finances"] = "on"
    client.post("/developpeur/permissions/enregistrer", data=cases)
    client.get("/auth/deconnexion")

    from app.models.permission import Permission
    lignes = Permission.query.all()
    assert [(p.ecole_id, p.role, p.module, p.autorise) for p in lignes] == [(1, "secretaire", "finances", True)]

    connecter(client, "s1@t.td")
    assert client.get("/finances/").status_code == 200
    client.get("/auth/deconnexion")
    connecter(client, "s2@t.td")
    assert client.get("/finances/").status_code == 403


def test_reglage_d_ecole_prime_sur_le_reglage_commun(app, db):
    from app.models.permission import Permission
    from app.services.permissions import role_a_acces
    from flask import g

    db.session.add_all([
        Permission(ecole_id=None, role="comptable", module="statistiques", autorise=False),
        Permission(ecole_id=1, role="comptable", module="statistiques", autorise=True),
    ])
    db.session.commit()
    with app.test_request_context():
        g.ecole_id = 1
        assert role_a_acces("comptable", "statistiques", [])
        g.ecole_id = 2
        assert not role_a_acces("comptable", "statistiques", ["comptable"])


def test_le_fondateur_ne_touche_pas_aux_zones_techniques(client, db, creer_utilisateur):
    from app.models.permission import Permission
    creer_utilisateur("Fondateur", "f@t.td", "fondateur")
    connecter(client, "f@t.td")
    client.post("/developpeur/permissions/enregistrer", data={"fondateur__sauvegarde": "on", "fondateur__gestion_roles": "on"})
    assert not Permission.query.filter(Permission.module.in_(["sauvegarde", "gestion_roles"])).count()


def test_revenir_au_reglage_commun(client, db, creer_utilisateur):
    from app.models.permission import Permission
    creer_utilisateur("Fondateur", "f@t.td", "fondateur")
    db.session.add(Permission(ecole_id=1, role="secretaire", module="finances", autorise=True))
    db.session.commit()
    connecter(client, "f@t.td")
    client.post("/developpeur/permissions/reinitialiser")
    assert Permission.query.count() == 0


def test_seuls_les_roles_prevus_reglent_les_permissions(client, creer_utilisateur):
    creer_utilisateur("Directeur", "d@t.td", "directeur_college")
    connecter(client, "d@t.td")
    assert client.get("/developpeur/permissions").status_code == 403
    assert client.post("/developpeur/permissions/enregistrer", data={}).status_code == 403


def _cases_par_defaut(roles, modules):
    from app.services.modules_par_defaut import ROLES_PAR_DEFAUT
    return {f"{r}__{m}": "on" for r in roles for m in modules if r in ROLES_PAR_DEFAUT.get(m, [])}


def test_le_fondateur_ne_regle_ni_son_role_ni_ce_qu_il_n_a_pas(client, app, db, creer_utilisateur):
    from app.models.permission import Permission
    from app.services.delegation import portee_matrice
    from app.services.permissions import vider_cache
    from flask import g

    # L'administrateur de la plateforme a retiré les salaires au fondateur.
    db.session.add(Permission(ecole_id=None, role="fondateur", module="salaires", autorise=False))
    db.session.commit()
    vider_cache()
    creer_utilisateur("Fondateur", "f@t.td", "fondateur")
    connecter(client, "f@t.td")
    page = _texte(client.get("/developpeur/permissions"))
    assert 'name="fondateur__' not in page and 'name="super_administrateur__' not in page
    assert 'name="secretaire__salaires"' not in page and 'name="secretaire__sauvegarde"' not in page
    assert 'name="secretaire__finances"' in page

    with app.test_request_context():
        g.ecole_id = 1
        roles, modules = portee_matrice("fondateur")
    cases = _cases_par_defaut(roles, modules)
    cases.update({"fondateur__salaires": "on", "secretaire__salaires": "on", "fondateur__gestion_roles": "on"})
    client.post("/developpeur/permissions/enregistrer", data=cases)
    assert [(p.ecole_id, p.role, p.module, p.autorise) for p in Permission.query.all()] == [(None, "fondateur", "salaires", False)]


def test_le_secretariat_regle_les_roles_de_base_hors_finances(client, app, db, creer_utilisateur):
    from app.models.permission import Permission
    from app.services.delegation import portee_matrice

    # Un réglage du fondateur, hors de la portée du secrétariat : il doit rester.
    db.session.add(Permission(ecole_id=1, role="comptable", module="eleves", autorise=True))
    db.session.commit()
    creer_utilisateur("Sec", "s@t.td", "secretaire")
    creer_utilisateur("Prof", "p@t.td", "enseignant")
    connecter(client, "s@t.td")
    page = _texte(client.get("/developpeur/permissions"))
    assert 'name="enseignant__alertes"' in page and 'name="eleve__bibliotheque"' in page
    for absent in ("enseignant__finances", "enseignant__caisse", "enseignant__salaires", "enseignant__statistiques",
                   "enseignant__gestion_roles", "secretaire__", "comptable__", "fondateur__", "directeur_college__"):
        assert f'name="{absent}' not in page
    assert "Permissions" in _texte(client.get("/"))

    roles, modules = portee_matrice("secretaire")
    cases = _cases_par_defaut(roles, modules)
    cases.update({"enseignant__alertes": "on", "enseignant__caisse": "on", "secretaire__finances": "on", "comptable__eleves": ""})
    client.post("/developpeur/permissions/enregistrer", data=cases)
    assert sorted((p.role, p.module, p.autorise) for p in Permission.query.all()) == [
        ("comptable", "eleves", True), ("enseignant", "alertes", True)]

    # « Revenir au réglage commun » n'efface que sa propre partie.
    client.post("/developpeur/permissions/reinitialiser")
    assert [(p.role, p.module) for p in Permission.query.all()] == [("comptable", "eleves")]
    client.get("/auth/deconnexion")


# ------------------------------------------------------- double authentification
@pytest.fixture
def double_auth(app, db):
    from app.models.ecole import Ecole
    ecole = db.session.get(Ecole, 1)
    ecole.double_authentification = True
    db.session.commit()
    app.config["AFFICHER_SECRETS_SANS_EMAIL"] = False
    return ecole


def _code_envoye(monkeypatch):
    envois = []

    def faux_envoi(destinataires, sujet, corps, **_):
        envois.append(corps)
        return True
    monkeypatch.setattr("app.auth.routes.envoyer_email", faux_envoi)
    return envois


def test_la_direction_doit_saisir_le_code_recu_par_email(client, double_auth, creer_utilisateur, monkeypatch):
    envois = _code_envoye(monkeypatch)
    creer_utilisateur("Fondateur", "f@t.td", "fondateur")
    r = client.post("/auth/connexion", data={"email": "f@t.td", "mot_de_passe": "p12345678"})
    assert r.headers["Location"].endswith("/auth/code-connexion")
    # Mot de passe juste mais pas encore de code : pas connecté.
    assert client.get("/eleves/").status_code in (302, 401, 403)
    code = re.search(r"\b(\d{6})\b", envois[-1]).group(1)
    assert _texte(client.post("/auth/code-connexion", data={"code": "000000" if code != "000000" else "111111"},
                              follow_redirects=True)).count("Code invalide") == 1
    r = client.post("/auth/code-connexion", data={"code": code, "se_souvenir": "on"})
    assert r.status_code == 302 and "appareil_confiance=" in r.headers.get("Set-Cookie", "")
    assert client.get("/eleves/").status_code == 200

    # Appareil de confiance : plus de code à la prochaine connexion.
    client.get("/auth/deconnexion")
    r = client.post("/auth/connexion", data={"email": "f@t.td", "mot_de_passe": "p12345678"})
    assert not r.headers["Location"].endswith("/auth/code-connexion")


def test_trop_de_codes_faux_ramene_a_la_connexion(client, double_auth, creer_utilisateur, monkeypatch):
    _code_envoye(monkeypatch)
    creer_utilisateur("Comptable", "c@t.td", "comptable")
    client.post("/auth/connexion", data={"email": "c@t.td", "mot_de_passe": "p12345678"})
    for _ in range(5):
        r = client.post("/auth/code-connexion", data={"code": "999999"})
    assert r.headers["Location"].endswith("/auth/connexion")
    assert client.get("/auth/code-connexion").headers["Location"].endswith("/auth/connexion")


def test_pas_de_code_pour_les_autres_roles_ni_sans_l_option(client, db, double_auth, creer_utilisateur, monkeypatch):
    _code_envoye(monkeypatch)
    creer_utilisateur("Prof", "p@t.td", "enseignant")
    r = client.post("/auth/connexion", data={"email": "p@t.td", "mot_de_passe": "p12345678"})
    assert r.headers["Location"].endswith("/")
    client.get("/auth/deconnexion")
    double_auth.double_authentification = False
    db.session.commit()
    creer_utilisateur("Fondateur", "f@t.td", "fondateur")
    r = client.post("/auth/connexion", data={"email": "f@t.td", "mot_de_passe": "p12345678"})
    assert not r.headers["Location"].endswith("/auth/code-connexion")


def test_sans_email_la_direction_n_entre_pas(client, double_auth, creer_utilisateur, monkeypatch):
    monkeypatch.setattr("app.auth.routes.envoyer_email", lambda *a, **k: False)
    creer_utilisateur("Fondateur", "f@t.td", "fondateur")
    r = client.post("/auth/connexion", data={"email": "f@t.td", "mot_de_passe": "p12345678"})
    assert r.status_code == 200 and "pas pu partir" in _texte(r)
    assert client.get("/eleves/").status_code in (302, 401, 403)


# ------------------------------------------------------------------ couleurs
def test_couleurs_de_l_ecole_appliquees_et_couleur_illisible_refusee(client, db, creer_utilisateur):
    from app.models.ecole import Ecole
    creer_utilisateur("Fondateur", "f@t.td", "fondateur")
    connecter(client, "f@t.td")
    assert ":root{--navy" not in _texte(client.get("/"))  # couleurs de la plateforme par défaut

    base = {"nom": "École Test", "sigle": "ET", "prefixe_matricule": "ET26"}
    client.post("/developpeur/parametres", data={**base, "couleur_theme": "#FFFF00", "couleur_accent": "#00A99D"})
    assert db.session.get(Ecole, 1).couleur_theme is None  # jaune : texte blanc illisible

    client.post("/developpeur/parametres", data={**base, "couleur_theme": "#7a1f1f", "couleur_accent": "#1f6b3a"})
    db.session.expire_all()
    assert db.session.get(Ecole, 1).couleur_theme == "#7A1F1F"
    page = _texte(client.get("/"))
    assert "--navy:#7A1F1F" in page and "--gold:#1F6B3A" in page

    client.post("/developpeur/parametres", data={**base, "couleurs_plateforme": "on",
                                                  "couleur_theme": "#7a1f1f", "couleur_accent": "#1f6b3a"})
    db.session.expire_all()
    assert db.session.get(Ecole, 1).couleur_theme is None


def test_contraste_des_couleurs():
    from app.services.theme import contraste_avec_blanc, verifier_couleur
    assert contraste_avec_blanc("#0F5FA6") > 4.5
    assert verifier_couleur("bleu", "Couleur", 4.5)[1]
    assert verifier_couleur("", "Couleur", 4.5) == (None, None)


# -------------------------------------------------------------- fiche de paie
def test_fiche_de_paie_detaillee_pour_la_compta_et_pour_l_interesse(client, db, creer_utilisateur):
    from app.models.salaire import Salaire
    creer_utilisateur("Compta", "c@t.td", "comptable")
    prof = creer_utilisateur("Prof", "p@t.td", "enseignant")
    creer_utilisateur("Autre", "a@t.td", "personnel")
    connecter(client, "c@t.td")
    client.post("/salaires/nouveau", data={"personnel_id": prof.id, "mois": 10, "annee": 2026, "montant": 100000,
                                           "primes": 15000, "motif_primes": "Heures sup", "retenues": 20000,
                                           "motif_retenues": "Avance"})
    salaire = Salaire.query.one()
    assert (salaire.salaire_base, salaire.montant) == (100000, 95000)
    r = client.get(f"/salaires/{salaire.id}/fiche")
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    client.get("/auth/deconnexion")

    connecter(client, "p@t.td")
    assert "Octobre 2026" in _texte(client.get("/salaires/mes-fiches"))
    assert client.get(f"/salaires/{salaire.id}/fiche").mimetype == "application/pdf"
    client.get("/auth/deconnexion")
    connecter(client, "a@t.td")
    assert client.get(f"/salaires/{salaire.id}/fiche").status_code == 403


def test_retenues_superieures_au_salaire_refusees(client, creer_utilisateur):
    from app.models.salaire import Salaire
    creer_utilisateur("Compta", "c@t.td", "comptable")
    prof = creer_utilisateur("Prof", "p@t.td", "enseignant")
    connecter(client, "c@t.td")
    r = client.post("/salaires/nouveau", data={"personnel_id": prof.id, "mois": 10, "annee": 2026,
                                               "montant": 50000, "retenues": 60000})
    assert "net à payer" in _texte(r) and Salaire.query.count() == 0


def test_ancien_salaire_sans_detail_garde_son_montant(app, db, creer_utilisateur):
    from app.models.salaire import Salaire
    prof = creer_utilisateur("Prof", "p@t.td", "enseignant")
    s = Salaire(personnel_id=prof.id, mois=9, annee=2026, montant=80000)
    db.session.add(s)
    db.session.commit()
    assert s.base == 80000
