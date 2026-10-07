"""Sauvegarde complète puis restauration d'un établissement."""

import io
import json
import zipfile
from datetime import date

from flask import g

from tests.conftest import connecter

TOUS = {"tous_etablissements": True}


def _peupler(db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.paiement import Paiement
    from app.models.mouvement_caisse import MouvementCaisse
    from app.models.ressource import Ressource
    from app.models.note import Note
    from app.models.message import Message
    from app.models.telephone import NumeroTelephone

    fond = creer_utilisateur("Fondateur", "f@t.com", "fondateur")
    parent = creer_utilisateur("Parent", "p@t.com", "parent")
    classe = creer_classe(nom="CM2", niveau=6, frais_inscription=10000)
    eleve = creer_eleve("Awa Sauvée", classe, matricule="ET26-CM2-001")
    eleve.date_naissance = date(2014, 2, 3)
    eleve.parents.append(parent)
    paiement = Paiement(eleve_id=eleve.id, montant=7500, mode="especes", echeance="inscription",
                        annee_scolaire=classe.annee_scolaire, enregistre_par_id=fond.id)
    db.session.add(paiement)
    db.session.flush()
    db.session.add_all([
        MouvementCaisse(date=date(2026, 9, 1), type="scolarite", libelle="Inscription Awa", recette=7500, depense=0,
                        automatique=True, origine_module="finances", origine_id=paiement.id, eleve_id=eleve.id),
        Ressource(titre="Cours", type="cours", nom_fichier="c.pdf", contenu=b"\x00\x01PDF\xff", type_mime="application/pdf",
                  consultation_sur_place=False, ajoute_par_id=fond.id),
        Note(eleve_id=eleve.id, classe_id=classe.id, matiere="Maths", valeur=15.5, bareme=20, trimestre="T1",
             annee_scolaire=classe.annee_scolaire),
        Message(parent_id=parent.id, auteur_id=parent.id, contenu="Bonjour"),
        NumeroTelephone(user_id=parent.id, numero="+23566000001", operateur="airtel"),
    ])
    db.session.commit()


def _sauvegarder(client):
    connecter(client, "dev@t.com")
    r = client.get("/sauvegarde/exporter")
    assert r.status_code == 200
    return r.get_data()


def test_sauvegarde_puis_restauration_complete(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.eleve import Eleve
    from app.models.user import User
    from app.models.paiement import Paiement
    from app.models.mouvement_caisse import MouvementCaisse
    from app.models.ressource import Ressource
    from app.models.note import Note
    from app.models.message import Message

    creer_utilisateur("Dev", "dev@t.com", "developpeur")
    _peupler(db, creer_utilisateur, creer_classe, creer_eleve)
    archive = _sauvegarder(client)

    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        donnees = json.loads(z.read("donnees.json"))
        assert donnees["version"] == 2 and len(donnees["tables"]["eleves"]) == 1
        assert "mot_de_passe_hash" not in z.read("users.csv").decode()

    # Catastrophe : on abîme les données, puis on restaure.
    db.session.remove()
    g.ecole_id = 1
    Note.query.delete()
    Eleve.query.one().nom_complet = "ABÎMÉ"
    db.session.commit()
    db.session.remove()
    g.pop("_login_user", None)  # artefact de test : compte gardé en mémoire entre deux requêtes

    r = client.post("/plateforme/1/restaurer", data={
        "confirmation": "et", "archive": (io.BytesIO(archive), "sauvegarde.zip"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert "restauré depuis la sauvegarde" in r.get_data(as_text=True)

    db.session.remove()
    g.ecole_id = 1
    eleve = Eleve.query.one()
    assert eleve.nom_complet == "Awa Sauvée" and eleve.date_naissance == date(2014, 2, 3)
    assert eleve.classe.nom == "CM2" and float(eleve.classe.frais_inscription) == 10000
    assert [p.email for p in eleve.parents] == ["p@t.com"]
    assert Note.query.one().valeur == 15.5
    assert Ressource.query.one().contenu == b"\x00\x01PDF\xff"
    assert Message.query.count() == 1
    paiement = Paiement.query.one()
    assert float(paiement.montant) == 7500 and paiement.eleve_id == eleve.id
    assert paiement.enregistre_par.email == "f@t.com"
    mouvement = MouvementCaisse.query.one()
    assert mouvement.origine_id == paiement.id and mouvement.date == date(2026, 9, 1)
    assert User.query.filter_by(role="developpeur").count() == 0  # le super-admin n'appartient à aucune école

    # Les comptes restaurés peuvent se reconnecter avec leur mot de passe.
    client.get("/auth/deconnexion")
    r = connecter(client, "f@t.com")
    assert "accueil-carte-ecole" in r.get_data(as_text=True)


def test_restauration_refusee_sans_confirmation(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.eleve import Eleve

    creer_utilisateur("Dev", "dev@t.com", "developpeur")
    _peupler(db, creer_utilisateur, creer_classe, creer_eleve)
    archive = _sauvegarder(client)
    r = client.post("/plateforme/1/restaurer", data={
        "confirmation": "mauvais", "archive": (io.BytesIO(archive), "s.zip"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert "Confirmation incorrecte" in r.get_data(as_text=True)
    db.session.remove()
    g.ecole_id = 1
    assert Eleve.query.count() == 1


def test_fichier_invalide_ne_change_rien(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.eleve import Eleve

    creer_utilisateur("Dev", "dev@t.com", "developpeur")
    _peupler(db, creer_utilisateur, creer_classe, creer_eleve)
    connecter(client, "dev@t.com")
    for contenu in (b"pas un zip", _zip({"autre.txt": "x"}), _zip({"donnees.json": "{"})):
        r = client.post("/plateforme/1/restaurer", data={
            "confirmation": "ET", "archive": (io.BytesIO(contenu), "s.zip"),
        }, content_type="multipart/form-data", follow_redirects=True)
        assert r.status_code == 200
        db.session.remove()
        g.ecole_id = 1
        assert Eleve.query.count() == 1


def test_conflit_avec_une_autre_ecole_annule_tout(client, db, creer_utilisateur, creer_classe, creer_eleve):
    """Restaurer la sauvegarde de l'école 1 dans l'école 2 alors que les
    comptes existent encore dans l'école 1 : refus, et l'école 2 garde ses données."""
    from app.models.ecole import Ecole
    from app.models.user import User

    creer_utilisateur("Dev", "dev@t.com", "developpeur")
    _peupler(db, creer_utilisateur, creer_classe, creer_eleve)
    db.session.add(Ecole(id=2, nom="Autre", sigle="AU", prefixe_matricule="AU26", actif=True))
    db.session.commit()
    creer_utilisateur("Fond B", "b@t.com", "fondateur", ecole_id=2)
    archive = _sauvegarder(client)
    r = client.post("/plateforme/2/restaurer", data={
        "confirmation": "AU", "archive": (io.BytesIO(archive), "s.zip"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert "Restauration annulée" in r.get_data(as_text=True)
    db.session.remove()
    g.ecole_id = None
    emails = {u.email for u in db.session.query(User).execution_options(**TOUS).all()}
    assert {"b@t.com", "f@t.com", "p@t.com"} <= emails


def test_restauration_reservee_au_super_administrateur(client, creer_utilisateur):
    creer_utilisateur("Fond", "f@t.com", "fondateur")
    connecter(client, "f@t.com")
    assert client.get("/plateforme/1/restaurer").status_code == 403


def _zip(fichiers):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        for nom, contenu in fichiers.items():
            z.writestr(nom, contenu)
    return tampon.getvalue()
