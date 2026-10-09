"""Diagnostic avant déploiement : numéros attribués sans doublon même en
simultané, suppression d'un compte qui a un historique, annonces,
dossiers d'élèves vus par les enseignants, textes trop longs, réglages
du serveur (clé secrète, nom de domaine, premier compte)."""

import glob
import io
import os
import re
import threading
from datetime import date, timedelta

import pytest

from tests.conftest import connecter, URL_POSTGRESQL


def _texte(reponse):
    return reponse.get_data(as_text=True)


# ------------------------------------------------------------------ numéros
def test_compteur_cree_puis_incremente(app, db):
    from flask import g
    from app.services.compteurs import prochain_numero

    g.ecole_id = 1
    appels = []
    assert prochain_numero("ESSAI", 2026, depart=lambda: appels.append(1) or 41) == 42
    assert prochain_numero("ESSAI", 2026, depart=lambda: appels.append(1) or 0) == 43
    assert prochain_numero("ESSAI", 2027) == 1
    assert len(appels) == 1  # le départ n'est calculé qu'à la création du compteur


def test_compteurs_separes_par_ecole(app, db):
    from flask import g
    from app.models.ecole import Ecole
    from app.services.compteurs import prochain_numero

    db.session.add(Ecole(id=2, nom="Autre", sigle="AU", prefixe_matricule="AU26", actif=True))
    db.session.commit()
    g.ecole_id = 1
    assert [prochain_numero("CERT", 2026) for _ in range(3)] == [1, 2, 3]
    db.session.commit()
    g.ecole_id = 2
    assert prochain_numero("CERT", 2026) == 1


@pytest.mark.skipif(not URL_POSTGRESQL, reason="simultanéité réelle : seulement sur PostgreSQL")
def test_paiements_et_inscriptions_simultanes_sans_doublon(app, db, creer_utilisateur, creer_classe, creer_eleve):
    from flask import g
    from app.models.classe import Classe
    from app.models.eleve import Eleve
    from app.models.paiement import Paiement
    from app.models.user import User
    from app.services.paiements import enregistrer_paiement

    comptable_id = creer_utilisateur("Compt", "compt@t.td", "comptable").id
    classe_id = creer_classe(nom="CP1", frais_inscription=100000).id
    eleves = [creer_eleve(f"Eleve {i}", db.session.get(Classe, classe_id), matricule=f"X{i}").id for i in range(16)]
    db.session.remove()
    erreurs = []

    def payer(eleve_id):
        with app.app_context():
            g.ecole_id = 1
            try:
                enregistrer_paiement(db.session.get(Eleve, eleve_id), 1000, "especes", "inscription",
                                     db.session.get(User, comptable_id))
            except Exception as erreur:  # noqa: BLE001 — on veut voir toute erreur
                db.session.rollback()
                erreurs.append(repr(erreur)[:120])
            finally:
                db.session.remove()

    def inscrire(rang):
        with app.app_context():
            g.ecole_id = 1
            try:
                classe = db.session.get(Classe, classe_id)
                db.session.add(Eleve(matricule=Eleve.generer_matricule(classe), nom_complet=f"Nouveau {rang}",
                                     classe_id=classe_id))
                db.session.commit()
            except Exception as erreur:  # noqa: BLE001
                db.session.rollback()
                erreurs.append(repr(erreur)[:120])
            finally:
                db.session.remove()

    for cible, arguments in ((payer, eleves), (inscrire, range(16))):
        fils = [threading.Thread(target=cible, args=(a,)) for a in arguments]
        [f.start() for f in fils]
        [f.join() for f in fils]

    assert erreurs == []
    g.ecole_id = 1
    numeros = [p.numero_recu for p in Paiement.query.all()]
    assert len(numeros) == 16 and len(set(numeros)) == 16
    matricules = [e.matricule for e in Eleve.query.filter(Eleve.nom_complet.like("Nouveau%")).all()]
    assert len(matricules) == 16 and len(set(matricules)) == 16


# ------------------------------------------------- suppression d'un compte
@pytest.fixture
def ecole_avec_historique(db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.cahier_textes import SeanceCahier
    from app.models.discipline import Incident
    from app.models.document_verifiable import DocumentVerifiable
    from app.models.enseignant import Enseignant, Affectation
    from app.models.evaluation import Evaluation
    from app.models.livre import Livre, Pret
    from app.models.note import Note
    from app.models.preinscription import PreInscription

    creer_utilisateur("Dev", "dev@t.td", "developpeur")
    prof = creer_utilisateur("Prof Sortant", "prof@t.td", "enseignant")
    secretaire = creer_utilisateur("Secrétaire", "sec@t.td", "secretaire")
    bibliothecaire = creer_utilisateur("Biblio", "bib@t.td", "bibliothecaire")
    classe = creer_classe(nom="6e", niveau=7)
    eleve = creer_eleve("Awa", classe)
    enseignant = Enseignant(user_id=prof.id)
    db.session.add(enseignant)
    db.session.commit()
    evaluation = Evaluation(classe_id=classe.id, matiere="Maths", trimestre="T1", annee_scolaire=classe.annee_scolaire,
                            titre="Devoir", date=date.today(), enseignant_id=enseignant.id)
    livre = Livre(titre="Roman")
    db.session.add_all([
        Affectation(enseignant_id=enseignant.id, classe_id=classe.id, matiere="Maths"), evaluation, livre,
        SeanceCahier(classe_id=classe.id, enseignant_id=enseignant.id, matiere="Maths", date=date.today(), contenu="Cours"),
        Incident(eleve_id=eleve.id, classe_id=classe.id, date=date.today(), type="retard", auteur_id=secretaire.id),
        PreInscription(reference="PI-AAAAAA", nom_candidat="Nouveau", nom_parent="Papa",
                       telephone_parent="+23566112233", traite_par_id=secretaire.id),
        DocumentVerifiable(code="AAAA-BBBB-CCCC", type_document="recu", cle_objet="recu:1", titre="Reçu",
                           emis_par_id=secretaire.id),
    ])
    db.session.commit()
    db.session.add_all([
        Note(eleve_id=eleve.id, classe_id=classe.id, matiere="Maths", valeur=12, bareme=20, trimestre="T1",
             annee_scolaire=classe.annee_scolaire, evaluation_id=evaluation.id, enseignant_id=enseignant.id),
        Pret(livre_id=livre.id, eleve_id=eleve.id, date_pret=date.today(),
             date_retour_prevue=date.today() + timedelta(days=7), prete_par_id=bibliothecaire.id),
    ])
    db.session.commit()
    return {"prof": prof.id, "sec": secretaire.id, "bib": bibliothecaire.id, "enseignant": enseignant.id,
            "classe": classe.id, "livre": livre.id}


def test_supprimer_des_comptes_qui_ont_un_historique(client, db, ecole_avec_historique):
    from app.models.cahier_textes import SeanceCahier
    from app.models.discipline import Incident
    from app.models.document_verifiable import DocumentVerifiable
    from app.models.evaluation import Evaluation
    from app.models.livre import Pret
    from app.models.note import Note
    from app.models.preinscription import PreInscription
    from app.models.user import User

    ids = ecole_avec_historique
    connecter(client, "dev@t.td")
    for cle in ("prof", "sec", "bib"):
        db.session.remove()
        r = client.post(f"/developpeur/utilisateur/{ids[cle]}/supprimer", follow_redirects=True)
        assert r.status_code == 200 and "supprimé définitivement" in _texte(r), cle

    db.session.remove()
    assert all(db.session.get(User, ids[cle]) is None for cle in ("prof", "sec", "bib"))
    # L'historique reste, simplement sans auteur.
    assert Note.query.one().enseignant_id is None and Evaluation.query.one().enseignant_id is None
    assert SeanceCahier.query.one().enseignant_id is None
    assert Incident.query.one().auteur_id is None and PreInscription.query.one().traite_par_id is None
    assert DocumentVerifiable.query.one().emis_par_id is None and Pret.query.one().prete_par_id is None


def test_suppression_refusee_quand_un_lien_obligatoire_existe(client, db, ecole_avec_historique):
    from app.models.livre import Pret
    from app.models.suivi_cours import SuiviCours
    from app.models.user import User

    ids = ecole_avec_historique
    db.session.add_all([
        SuiviCours(classe_id=ids["classe"], enseignant_id=ids["enseignant"], matiere="Maths", chapitre="Fractions"),
        Pret(livre_id=ids["livre"], user_id=ids["sec"], date_pret=date.today(),
             date_retour_prevue=date.today() + timedelta(days=7)),
    ])
    db.session.commit()
    connecter(client, "dev@t.td")

    r = client.post(f"/developpeur/utilisateur/{ids['prof']}/supprimer", follow_redirects=True)
    assert r.status_code == 200 and "suivis de cours" in _texte(r) and "verrouille son compte" in _texte(r)
    r = client.post(f"/developpeur/utilisateur/{ids['sec']}/supprimer", follow_redirects=True)
    assert r.status_code == 200 and "livres empruntés" in _texte(r)

    db.session.remove()
    assert db.session.get(User, ids["prof"]) is not None and db.session.get(User, ids["sec"]) is not None
    # Rien n'a été modifié en chemin : la tentative est annulée en entier.
    from app.models.note import Note
    assert Note.query.one().enseignant_id == ids["enseignant"]


# ----------------------------------------------------------------- annonces
def _publier(client, titre, destinataire, fichier=None):
    donnees = {"titre": titre, "contenu": "Ligne 1\nLigne 2", "destinataire": destinataire}
    if fichier:
        donnees["fichier"] = fichier
    return client.post("/communication/nouvelle", data=donnees, content_type="multipart/form-data", follow_redirects=True)


def test_la_direction_voit_les_annonces_qu_elle_adresse_aux_parents(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.annonce import Annonce

    creer_utilisateur("Fondateur", "fond@t.td", "fondateur")
    creer_utilisateur("Secrétaire", "sec@t.td", "secretaire")
    prof = creer_utilisateur("Prof Parent", "prof@t.td", "enseignant")
    creer_utilisateur("Autre Prof", "prof2@t.td", "enseignant")
    creer_utilisateur("Parent", "parent@t.td", "parent")
    creer_utilisateur("Comptable", "compta@t.td", "comptable")
    eleve = creer_eleve("Enfant du prof", creer_classe())
    eleve.parents.append(prof)
    db.session.commit()

    connecter(client, "fond@t.td")
    assert "Annonce publiée" in _texte(_publier(client, "Réunion des parents", "parent"))
    page = _texte(client.get("/communication/"))
    assert "Réunion des parents" in page and "Parents" in page and "Supprimer" in page
    annonce_id = Annonce.query.one().id
    assert client.get(f"/communication/{annonce_id}").status_code == 200

    def voit(email):
        client.get("/auth/deconnexion")
        connecter(client, email)
        return "Réunion des parents" in _texte(client.get("/communication/")), client.get(f"/communication/{annonce_id}").status_code

    assert voit("sec@t.td") == (True, 200)       # le secrétariat gère toutes les annonces
    assert voit("parent@t.td") == (True, 200)
    assert voit("prof@t.td") == (True, 200)      # enseignant, mais aussi parent d'élève
    assert voit("prof2@t.td") == (False, 403)
    assert voit("compta@t.td") == (False, 403)


def test_un_enseignant_retrouve_ses_propres_annonces(client, db, creer_utilisateur):
    creer_utilisateur("Prof", "prof@t.td", "enseignant")
    creer_utilisateur("Collègue", "prof2@t.td", "enseignant")
    connecter(client, "prof@t.td")
    _publier(client, "Devoir de vacances", "eleve")
    page = _texte(client.get("/communication/"))
    assert "Devoir de vacances" in page and "Supprimer" in page
    client.get("/auth/deconnexion")
    connecter(client, "prof2@t.td")
    assert "Devoir de vacances" not in _texte(client.get("/communication/"))


def test_piece_jointe_enregistree_en_base_et_dans_la_sauvegarde(app, client, db, creer_utilisateur):
    from flask import g
    from sqlalchemy import inspect
    from app.models.annonce import Annonce
    from app.models.ecole import Ecole
    from app.services.sauvegarde import exporter_ecole

    creer_utilisateur("Fondateur", "fond@t.td", "fondateur")
    creer_utilisateur("Parent", "parent@t.td", "parent")
    creer_utilisateur("Élève", "eleve@t.td", "eleve")
    connecter(client, "fond@t.td")
    _publier(client, "Liste des fournitures", "parent", (io.BytesIO(b"%PDF-1.4 fournitures"), "Liste fournitures.pdf"))

    db.session.remove()
    annonce = Annonce.query.one()
    assert annonce.nom_fichier == "Liste_fournitures.pdf" and "fichier" in inspect(annonce).unloaded
    assert annonce.fichier == b"%PDF-1.4 fournitures" and annonce.fichier_mime == "application/pdf"
    assert not os.path.exists(os.path.join(app.instance_path, "communication", "Liste_fournitures.pdf"))

    client.get("/auth/deconnexion")
    connecter(client, "parent@t.td")
    r = client.get(f"/communication/{annonce.id}/fichier")
    assert r.status_code == 200 and r.data == b"%PDF-1.4 fournitures"
    assert "attachment" in r.headers["Content-Disposition"] and "Liste_fournitures.pdf" in r.headers["Content-Disposition"]
    client.get("/auth/deconnexion")
    connecter(client, "eleve@t.td")
    assert client.get(f"/communication/{annonce.id}/fichier").status_code == 403

    g.ecole_id = 1
    sauvegarde = exporter_ecole(db.session.get(Ecole, 1))
    assert sauvegarde["tables"]["annonces"][0]["fichier"]  # contenu présent (base64)


# -------------------------------------------- dossiers élèves et enseignants
def test_un_enseignant_ne_voit_que_les_dossiers_de_ses_classes(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.enseignant import Enseignant, Affectation

    prof = creer_utilisateur("Prof", "prof@t.td", "enseignant")
    sixieme, cinquieme = creer_classe(nom="6e", niveau=7), creer_classe(nom="5e", niveau=8)
    mien = creer_eleve("Awa Mienne", sixieme, matricule="ET26-6E-001")
    autre = creer_eleve("Ben Autre", cinquieme, matricule="ET26-5E-001")
    autre.telephone_parent = "66 99 88 77"
    enseignant = Enseignant(user_id=prof.id)
    db.session.add(enseignant)
    db.session.commit()
    db.session.add(Affectation(enseignant_id=enseignant.id, classe_id=sixieme.id, matiere="Maths"))
    db.session.commit()
    mien_id, autre_id = mien.id, autre.id

    connecter(client, "prof@t.td")
    assert client.get(f"/eleves/{mien_id}").status_code == 200
    assert client.get(f"/eleves/{autre_id}").status_code == 403
    liste = _texte(client.get("/eleves/"))
    assert "Awa Mienne" in liste and "Ben Autre" not in liste
    recherche = _texte(client.get("/recherche?q=Ben"))
    assert "Ben Autre" not in recherche
    assert "Awa Mienne" in _texte(client.get("/recherche?q=Awa"))


# ------------------------------------------------------------------- emails
def test_les_adresses_techniques_ne_recoivent_jamais_d_email(app, monkeypatch):
    from app.extensions import envoyer_email

    envois = []

    class Reponse:
        status_code = 201

    monkeypatch.setattr("requests.post", lambda url, **k: envois.append(k["json"]) or Reponse())
    app.config["BREVO_API_KEY"] = "cle-test"
    assert envoyer_email(["et26-cp1-001@eleves.local", " parent@test.td ", "x@eleves.omega-academie.local"], "Sujet", "Corps") is True
    assert envois[0]["to"] == [{"email": "parent@test.td"}]
    assert envoyer_email(["seul@eleves.local"], "Sujet", "Corps") is False and len(envois) == 1


# ------------------------------------------------------- textes trop longs
def test_texte_trop_long_refuse_avec_le_nom_du_champ(client, db, creer_utilisateur):
    from app.models.mouvement_caisse import MouvementCaisse

    creer_utilisateur("Compt", "compt@t.td", "comptable")
    connecter(client, "compt@t.td")
    r = client.post("/caisse/nouveau", data={
        "type": "Divers", "libelle": "Achat", "depense": "500", "recette": "", "observation": "x" * 301,
        "date": date.today().isoformat(),
    })
    assert r.status_code == 400
    assert "observation" in _texte(r) and "300" in _texte(r)
    db.session.rollback()
    assert MouvementCaisse.query.count() == 0


def test_controle_des_longueurs_ne_gene_pas_les_textes_normaux(app, db, creer_classe, creer_eleve):
    from app.services.controles import TexteTropLong

    eleve = creer_eleve("Awa", creer_classe())
    eleve.adresse = "a" * 200          # pile la limite : accepté
    db.session.commit()
    eleve.adresse = "a" * 201
    with pytest.raises(TexteTropLong) as erreur:
        db.session.commit()
    assert erreur.value.champ == "adresse" and erreur.value.maximum == 200
    db.session.rollback()


# ------------------------------------------------------ réglages du serveur
def test_cle_secrete_faible_remplacee_par_une_cle_durable(tmp_path):
    from app import _cle_secrete_faible, _cle_secrete_durable

    assert all(_cle_secrete_faible(c) for c in (None, "", "change-this-in-production", "courte"))
    assert not _cle_secrete_faible("f3b1c0d2e4a59687f3b1c0d2e4a59687")

    class FausseApplication:
        instance_path = str(tmp_path)

    premiere = _cle_secrete_durable(FausseApplication)
    assert len(premiere) == 64 and _cle_secrete_durable(FausseApplication) == premiere  # stable aux redémarrages
    assert oct(os.stat(tmp_path / "cle_secrete").st_mode & 0o777) == "0o600"


def test_nom_de_domaine_inconnu_refuse(app, client):
    app.config["HOTES_AUTORISES"] = ["ecole.example"]
    assert client.get("/auth/connexion", headers={"Host": "ecole.example"}).status_code == 200
    assert client.get("/auth/connexion", headers={"Host": "ecole.example:443"}).status_code == 200
    r = client.get("/auth/mot-de-passe-oublie", headers={"Host": "pirate.example"})
    assert r.status_code == 400 and "non reconnue" in _texte(r)
    assert client.get("/sante", headers={"Host": "10.0.0.5"}).status_code == 200   # surveillance du serveur
    app.config["HOTES_AUTORISES"] = []
    assert client.get("/auth/connexion", headers={"Host": "pirate.example"}).status_code == 200


def test_premier_compte_en_ligne_exige_la_cle_d_installation(app, client, db):
    from app.models.user import User

    app.config["EXIGER_CLE_INSTALLATION"] = True
    donnees = {"nom_complet": "Admin", "email": "admin@t.td", "mot_de_passe": "motdepasse1", "confirmation": "motdepasse1"}

    app.config["CLE_INSTALLATION"] = ""
    page = _texte(client.get("/auth/premiere-configuration"))
    assert "creer-compte-initial" in page and 'name="mot_de_passe"' not in page
    client.post("/auth/premiere-configuration", data=donnees)
    assert User.query.count() == 0

    app.config["CLE_INSTALLATION"] = "cle-du-serveur-2026"
    assert 'name="cle_installation"' in _texte(client.get("/auth/premiere-configuration"))
    r = client.post("/auth/premiere-configuration", data={**donnees, "cle_installation": "mauvaise"})
    assert "incorrecte" in _texte(r) and User.query.count() == 0
    client.post("/auth/premiere-configuration", data={**donnees, "cle_installation": "cle-du-serveur-2026"})
    compte = User.query.one()
    assert compte.role == "developpeur" and compte.statut == "actif"


def test_commande_creer_compte_initial(app, db):
    from sqlalchemy import select
    from app.models.user import User

    lancer = app.test_cli_runner().invoke
    r = lancer(args=["creer-compte-initial", "--nom", "Admin", "--email", "Admin@T.td", "--mot-de-passe", "court"])
    assert r.exit_code != 0 and "8 caractères" in r.output
    r = lancer(args=["creer-compte-initial", "--nom", "Admin", "--email", "Admin@T.td", "--mot-de-passe", "motdepasse1"])
    assert r.exit_code == 0, r.output
    compte = db.session.execute(select(User).execution_options(tous_etablissements=True)).scalar_one()
    assert (compte.email, compte.role, compte.statut, compte.ecole_id) == ("admin@t.td", "developpeur", "actif", None)
    r = lancer(args=["creer-compte-initial", "--nom", "Bis", "--email", "admin@t.td", "--mot-de-passe", "motdepasse1"])
    assert r.exit_code != 0 and "existe déjà" in r.output


def test_gunicorn_impose_la_production(monkeypatch):
    import runpy

    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for valeur in ("development", "", None):
        if valeur is None:
            monkeypatch.delenv("FLASK_ENV", raising=False)
        else:
            monkeypatch.setenv("FLASK_ENV", valeur)
        reglages = runpy.run_path(os.path.join(racine, "gunicorn.conf.py"))
        assert os.environ["FLASK_ENV"] == "production"
        assert reglages["preload_app"] is True and reglages["workers"] >= 1


# ----------------------------------------------------- garde-fous permanents
def test_tous_les_formulaires_portent_leur_jeton(app):
    """Les tests tournent sans contrôle du jeton de formulaire : un
    formulaire qui l'oublierait ne serait vu qu'en production (erreur
    « page expirée » à chaque envoi)."""
    dossier = os.path.join(app.root_path, "templates")

    def contenu(chemin, profondeur=0):
        source = open(chemin, encoding="utf-8").read()
        if profondeur < 3:  # on déplie les morceaux inclus
            for inclus in re.findall(r'{%\s*include\s+"([^"]+)"', source):
                source = source.replace(f'include "{inclus}"', contenu(os.path.join(dossier, inclus), profondeur + 1), 1)
        return source

    fautifs, total = [], 0
    for chemin in glob.glob(os.path.join(dossier, "**", "*.html"), recursive=True):
        source = contenu(chemin)
        for formulaire in re.finditer(r"<form\b[^>]*>", source, flags=re.S | re.I):
            if not re.search(r'method\s*=\s*["\']?post', formulaire.group(0), flags=re.I):
                continue
            total += 1
            fin = source.find("</form>", formulaire.end())
            if "csrf_token" not in source[formulaire.end():fin if fin > 0 else formulaire.end() + 4000]:
                fautifs.append(os.path.relpath(chemin, dossier))
    assert total > 80 and fautifs == []


def test_sauvegarde_lisible_couvre_toutes_les_tables_sans_secret(client, db, creer_utilisateur):
    import zipfile

    creer_utilisateur("Dev", "dev@t.td", "developpeur")
    connecter(client, "dev@t.td")
    archive = zipfile.ZipFile(io.BytesIO(client.get("/sauvegarde/exporter").data))
    noms = set(archive.namelist())
    assert {"users.csv", "eleves.csv", "incidents.csv", "seances_cahier.csv", "prets.csv", "livres.csv",
            "preinscriptions.csv", "evenements_calendrier.csv", "donnees.json"} <= noms
    entete = archive.read("users.csv").decode().splitlines()[0]
    assert "email" in entete and "mot_de_passe_hash" not in entete and "code_2fa" not in entete
