"""Corrections de l'audit d'octobre 2026 (lot 1 : sécurité)."""

import io

from tests.conftest import connecter


def _texte(r):
    return r.get_data(as_text=True)


def test_directeur_de_cycle_reste_dans_son_cycle(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.enseignant import Enseignant, Affectation

    directeur = creer_utilisateur("Dir Prim", "d@t.td", "directeur_primaire")
    prof = creer_utilisateur("Prof", "p@t.td", "enseignant")
    cm2 = creer_classe("CM2", 5)
    sixieme = creer_classe("6e", 7)
    collegien = creer_eleve("Collégien", sixieme)
    ens = Enseignant(user_id=prof.id)
    db.session.add(ens)
    db.session.commit()
    connecter(client, "d@t.td")

    assert client.post(f"/enseignants/{ens.id}/affecter", data={"classe_id": sixieme.id, "matiere": "Français"}).status_code == 403
    client.post(f"/enseignants/{ens.id}/affecter", data={"classe_id": cm2.id, "matiere": "Français"})
    client.post(f"/enseignants/{ens.id}/affecter", data={"classe_id": cm2.id, "matiere": "Français"})
    assert Affectation.query.count() == 1  # pas de doublon

    r = client.post("/eleves/nouveau", data={"nom_complet": "Intrus", "classe_id": sixieme.id}, follow_redirects=True)
    assert "Classe introuvable" in _texte(r)
    assert client.post(f"/eleves/{collegien.id}/parent/ajouter", data={"parent_id": directeur.id}).status_code == 403
    assert client.post(f"/eleves/{collegien.id}/passage").status_code == 403

    # Se lier soi-même comme parent, même dans son cycle : refusé.
    primaire = creer_eleve("Écolier", cm2)
    r = client.post(f"/eleves/{primaire.id}/parent/ajouter", data={"parent_id": directeur.id}, follow_redirects=True)
    assert "Tu ne peux pas te lier toi-même" in _texte(r)

    # Retirer une affectation coupe l'accès de l'enseignant.
    affectation = Affectation.query.one()
    client.post(f"/enseignants/affectation/{affectation.id}/retirer")
    assert Affectation.query.count() == 0

    export = client.get("/enseignants/export/csv")
    assert export.status_code == 200


def test_code_de_connexion_limite_en_base(client, app, db, creer_utilisateur):
    from app.models.user import User
    from app.models.ecole import Ecole

    db.session.get(Ecole, 1).double_authentification = True
    db.session.commit()
    creer_utilisateur("Fond", "f@t.td", "fondateur")
    client.post("/auth/connexion", data={"email": "f@t.td", "mot_de_passe": "p12345678"})
    cookie_initial = client.get_cookie("session").value
    for _ in range(5):
        # Rejouer l'ancien cookie (compteur à zéro) ne remet plus le compteur à zéro.
        client.set_cookie("session", cookie_initial)
        client.post("/auth/code-connexion", data={"code": "000000"})
    db.session.remove()
    assert User.query.filter_by(email="f@t.td").one().code_2fa is None


def test_changer_de_mot_de_passe_deconnecte_les_autres_appareils(app, db, creer_utilisateur):
    creer_utilisateur("Sec", "s@t.td", "secretaire")
    telephone, ordinateur = app.test_client(), app.test_client()
    connecter(telephone, "s@t.td")
    connecter(ordinateur, "s@t.td")
    r = ordinateur.post("/profil/mot-de-passe", data={"mot_de_passe_actuel": "p12345678", "nouveau_mot_de_passe": "nouveau12345",
                                                       "confirmation": "nouveau12345"}, follow_redirects=True)
    assert "autres appareils" in _texte(r)
    assert ordinateur.get("/eleves/").status_code == 200
    from flask import g
    g.pop("_login_user", None)  # en test, le contexte (et donc g) est partagé entre les deux navigateurs
    assert telephone.get("/eleves/").status_code in (302, 401)


def test_compte_verrouille_pendant_la_session_est_deconnecte(client, db, creer_utilisateur):
    sec = creer_utilisateur("Sec", "s@t.td", "secretaire")
    connecter(client, "s@t.td")
    sec.statut = "verrouille"
    db.session.commit()
    assert client.get("/eleves/").status_code == 302


def test_verrouillage_selon_le_rang(client, db, creer_utilisateur):
    creer_utilisateur("Fond", "f@t.td", "fondateur")
    admin = creer_utilisateur("Admin", "a@t.td", "administrateur_general")
    attente = creer_utilisateur("Nouveau", "n@t.td", "parent", statut="en_attente")
    from app.models.user import User
    fondateur = User.query.filter_by(email="f@t.td").one()
    db.session.add(__import__("app.models.permission", fromlist=["Permission"]).Permission(
        ecole_id=None, role="administrateur_general", module="gestion_roles", autorise=True))
    db.session.commit()
    connecter(client, "a@t.td")
    r = client.post(f"/developpeur/utilisateur/{fondateur.id}/verrouiller", follow_redirects=True)
    assert "égal ou supérieur" in _texte(r)
    r = client.post(f"/developpeur/utilisateur/{attente.id}/verrouiller", follow_redirects=True)
    assert "Demandes de comptes" in _texte(r)
    db.session.remove()
    assert User.query.filter_by(email="f@t.td").one().statut == "actif"
    assert User.query.filter_by(email="n@t.td").one().statut == "en_attente"
    assert admin.id


def test_deconnexion_par_formulaire_seulement(client, creer_utilisateur):
    creer_utilisateur("Sec", "s@t.td", "secretaire")
    connecter(client, "s@t.td")
    assert "Me déconnecter" in _texte(client.get("/auth/deconnexion"))
    assert client.get("/eleves/").status_code == 200  # toujours connecté
    client.post("/auth/deconnexion")
    assert client.get("/eleves/").status_code == 302


def test_piece_jointe_d_annonce_jamais_lue_sur_le_disque(client, app, db, creer_utilisateur):
    import os
    from app.models.annonce import Annonce

    creer_utilisateur("Sec", "s@t.td", "secretaire")
    dossier = os.path.join(app.instance_path, "communication")
    os.makedirs(dossier, exist_ok=True)
    with open(os.path.join(dossier, "secret.pdf"), "wb") as f:
        f.write(b"autre ecole")
    annonce = Annonce(titre="T", contenu="C", destinataire="tous", nom_fichier="secret.pdf", fichier=b"")
    db.session.add(annonce)
    db.session.commit()
    connecter(client, "s@t.td")
    assert client.get(f"/communication/{annonce.id}/fichier").status_code == 404
    client.post(f"/communication/{annonce.id}/supprimer")
    assert os.path.exists(os.path.join(dossier, "secret.pdf"))  # jamais effacé depuis une école
    os.remove(os.path.join(dossier, "secret.pdf"))

    r = client.post("/communication/nouvelle", data={"titre": "Vide", "contenu": "x", "destinataire": "tous",
                                                     "fichier": (io.BytesIO(b""), "vide.pdf")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert "est vide" in _texte(r)
    r = client.post("/communication/nouvelle", data={"titre": "Arabe", "contenu": "x", "destinataire": "tous",
                                                     "fichier": (io.BytesIO(b"%PDF"), "دروس.pdf")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert Annonce.query.filter_by(titre="Arabe").one().nom_fichier.endswith(".pdf")


def test_bibliotheque_public_et_verrou(client, db, creer_utilisateur):
    from app.models.ressource import Ressource

    biblio = creer_utilisateur("Biblio", "b@t.td", "bibliothecaire")
    creer_utilisateur("Prof", "p@t.td", "enseignant")
    creer_utilisateur("Parent", "pa@t.td", "parent")
    corrige = Ressource(titre="Corrigé", type="cours", nom_fichier="c.pdf", contenu=b"%PDF", public="personnel",
                        ajoute_par_id=biblio.id, consultation_sur_place=True)
    db.session.add(corrige)
    db.session.commit()
    connecter(client, "p@t.td")
    assert client.post(f"/bibliotheque/{corrige.id}/verrouiller").status_code == 403
    assert "Corrigé" in _texte(client.get("/bibliotheque/"))
    sur_place = client.get(f"/bibliotheque/{corrige.id}/telecharger")
    assert sur_place.headers["Cache-Control"] == "no-store"
    client.post("/auth/deconnexion")
    connecter(client, "pa@t.td")
    assert "Corrigé" not in _texte(client.get("/bibliotheque/"))
    assert client.get(f"/bibliotheque/{corrige.id}/telecharger").status_code == 404


def test_quota_de_stockage(client, app, db, creer_utilisateur):
    from app.models.ecole import Ecole

    creer_utilisateur("Biblio", "b@t.td", "bibliothecaire")
    db.session.get(Ecole, 1).quota_stockage = 1000
    db.session.commit()
    connecter(client, "b@t.td")
    r = client.post("/bibliotheque/nouvelle", data={"titre": "Gros", "type": "cours", "fichier": (io.BytesIO(b"x" * 2000), "g.pdf")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert "Espace de stockage plein" in _texte(r)
    r = client.post("/bibliotheque/nouvelle", data={"titre": "Petit", "type": "cours", "fichier": (io.BytesIO(b"x" * 500), "p.pdf")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert "Ressource ajoutée" in _texte(r)
    from flask import g
    from app.services.stockage import espace_utilise
    with app.test_request_context():
        g.ecole_id = 1
        assert espace_utilise(1) == 500


def test_classe_modifiee_ou_supprimee_si_vide(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.classe import Classe

    creer_utilisateur("Sec", "s@t.td", "secretaire")
    vide = creer_classe("CE1 B", 3)
    pleine = creer_classe("CE2", 4)
    creer_eleve("Élève", pleine)
    id_vide, id_pleine = vide.id, pleine.id
    connecter(client, "s@t.td")
    client.post(f"/classes/{vide.id}/modifier", data={"nom": "CE1 C", "niveau": 3})
    assert db.session.get(Classe, vide.id).nom == "CE1 C"
    r = client.post(f"/classes/{pleine.id}/supprimer", follow_redirects=True)
    assert "n'est pas vide" in _texte(r)
    client.post(f"/classes/{id_vide}/supprimer")
    db.session.remove()
    assert db.session.get(Classe, id_vide) is None and db.session.get(Classe, id_pleine)
    from flask import g
    g.pop("_login_user", None)
    r = client.post("/classes/nouvelle", data={"nom": "CM1", "niveau": 4, "annee_scolaire": "2026"}, follow_redirects=True)
    assert "2027-2028" in _texte(r)


def test_secretaire_valide_l_eleve_qui_cree_son_compte(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from datetime import date

    eleve = creer_eleve("Moussa", creer_classe("CM1", 4), matricule="ET26-CM1-001")
    eleve.date_naissance = date(2014, 5, 20)
    db.session.commit()
    r = client.post("/auth/inscription", data={"role": "eleve", "ecole_id": "1", "matricule": "ET26-CM1-001",
                                               "date_naissance_eleve": "2014-05-20", "mot_de_passe": "eleve12345",
                                               "confirmation": "eleve12345"}, follow_redirects=True)
    assert "activé après vérification" in _texte(r)
