"""Calculs groupés (mêmes résultats, beaucoup moins de requêtes) et
réglages de production : serveur web en amont, permissions partagées
entre processus, sauvegarde planifiée."""

import json
import os
import zipfile

from sqlalchemy import event
from sqlalchemy.engine import Engine


class CompteurRequetes:
    def __enter__(self):
        self.nombre = 0
        event.listen(Engine, "before_cursor_execute", self._compter)
        return self

    def _compter(self, *_):
        self.nombre += 1

    def __exit__(self, *_):
        event.remove(Engine, "before_cursor_execute", self._compter)


def _ecole_notee(db, creer_classe, creer_eleve, effectif=30):
    from app.models.bulletin import CoefficientMatiere
    from app.models.note import Note

    cm2, sixieme = creer_classe(nom="CM2", niveau=6), creer_classe(nom="6e", niveau=7)
    eleves = []
    for i in range(effectif):
        classe = (cm2, sixieme)[i % 2]
        eleve = creer_eleve(f"Eleve {i:02d}", classe, sexe="MF"[i % 2], matricule=f"M{i:02d}")
        eleves.append(eleve)
        if i % 5 == 0:
            continue  # quelques élèves sans note
        bareme = 10 if classe is cm2 else 20
        for trimestre, maths, francais in (("T1", 3 + i % 7, 4 + i % 5), ("T2", 2 + i % 8, 5)):
            db.session.add_all([
                Note(eleve_id=eleve.id, classe_id=classe.id, matiere="Maths", valeur=min(maths, bareme),
                     bareme=bareme, trimestre=trimestre, annee_scolaire=classe.annee_scolaire),
                Note(eleve_id=eleve.id, classe_id=classe.id, matiere="Français", valeur=min(francais, bareme),
                     bareme=bareme, trimestre=trimestre, annee_scolaire=classe.annee_scolaire),
            ])
    db.session.add(CoefficientMatiere(classe_id=sixieme.id, matiere="Maths", coefficient=4))
    db.session.commit()
    return eleves, cm2.annee_scolaire


def test_moyennes_groupees_identiques_au_calcul_par_eleve(app, db, creer_classe, creer_eleve):
    from app.services.moyennes import moyenne_et_reussite, moyennes_et_reussites

    eleves, annee = _ecole_notee(db, creer_classe, creer_eleve)
    un_par_un = {e.id: moyenne_et_reussite(e, annee) for e in eleves}

    with CompteurRequetes() as compteur:
        groupees = moyennes_et_reussites(eleves, annee)

    assert groupees == un_par_un
    assert sum(1 for m, _ in groupees.values() if m is None) == 6
    assert compteur.nombre <= 5  # au lieu de trois requêtes par élève


def test_statistiques_et_alertes_en_quelques_requetes(app, db, creer_classe, creer_eleve):
    from app.models.absence import Absence
    from app.models.eleve import Eleve
    from app.services.alertes import eleves_absences_frequentes, eleves_moyenne_faible
    from app.services.moyennes import moyenne_et_reussite
    from app.services.statistiques import stats_reussite, tableau_par_sexe
    from datetime import date

    eleves, annee = _ecole_notee(db, creer_classe, creer_eleve)
    for jour in (1, 2, 3):
        db.session.add(Absence(eleve_id=eleves[1].id, classe_id=eleves[1].classe_id, date=date(2026, 10, jour)))
    db.session.add(Absence(eleve_id=eleves[2].id, classe_id=eleves[2].classe_id, date=date(2026, 10, 1)))
    db.session.commit()
    attendu_faibles = sorted(e.id for e in eleves if moyenne_et_reussite(e, annee)[1] is False)

    eleves = Eleve.query.all()
    [e.classe for e in eleves]
    with CompteurRequetes() as compteur:
        tableau = tableau_par_sexe(eleves, annee)
        globales = stats_reussite(eleves, annee)
        faibles = eleves_moyenne_faible(eleves, annee)
        absents = eleves_absences_frequentes(eleves)

    assert compteur.nombre <= 15
    assert tableau["Total"]["effectif"] == 30 and globales["nb_avec_notes"] == 24
    assert tableau["Total"]["taux_reussite"] == globales["taux_reussite"]
    assert sorted(l["eleve"].id for l in faibles) == attendu_faibles and attendu_faibles
    assert [(l["eleve"].nom_complet, l["nb_absences"]) for l in absents] == [("Eleve 01", 3)]


def test_resumes_de_paiement_groupes_identiques(app, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.eleve import Eleve
    from app.services.paiements import enregistrer_paiement, resume_paiements, resumes_paiements

    comptable = creer_utilisateur("Compt", "compt@test.com", "comptable")
    classe = creer_classe(frais_inscription=10000, frais_tranche1=5000)
    eleves = [creer_eleve(f"E{i}", classe, matricule=f"M{i}") for i in range(6)]
    eleves[0].remise_pourcent = 25
    db.session.commit()
    for i, eleve in enumerate(eleves[:4]):
        enregistrer_paiement(eleve, 2500 * (i + 1), "especes", "inscription", comptable)

    attendus = {e.id: resume_paiements(e) for e in eleves}
    eleves = Eleve.query.all()
    [e.classe for e in eleves]
    with CompteurRequetes() as compteur:
        groupes = resumes_paiements(eleves)
    assert groupes == attendus and compteur.nombre == 1


def test_permissions_relues_apres_le_delai_seulement(app, db):
    from app.models.permission import Permission
    from app.services.permissions import role_a_acces, vider_cache

    app.config["PERMISSIONS_CACHE_SECONDES"] = 60
    vider_cache()
    assert role_a_acces("secretaire", "finances", ["comptable"]) is False
    with CompteurRequetes() as compteur:
        role_a_acces("secretaire", "finances", ["comptable"])
        role_a_acces("comptable", "finances", ["comptable"])
    assert compteur.nombre == 0  # table vide : plus de relecture à chaque vérification

    db.session.add(Permission(role="secretaire", module="finances", autorise=True))
    db.session.commit()
    assert role_a_acces("secretaire", "finances", ["comptable"]) is False  # copie encore valable
    vider_cache()  # ce que fait l'écran des permissions en enregistrant
    assert role_a_acces("secretaire", "finances", ["comptable"]) is True

    app.config["PERMISSIONS_CACHE_SECONDES"] = 0  # délai écoulé : relecture
    db.session.query(Permission).delete()
    db.session.commit()
    assert role_a_acces("secretaire", "finances", ["comptable"]) is False


def test_derriere_un_serveur_web_https_et_adresse_du_visiteur(monkeypatch):
    import config
    from app import create_app
    from flask import request

    monkeypatch.setattr(config.Config, "PROXY_COUCHES", 1)
    application = create_app("testing")
    vus = {}

    @application.route("/_qui")
    def qui():
        vus.update(adresse=request.remote_addr, https=request.is_secure, hote=request.host)
        return "ok"

    en_tetes = {"X-Forwarded-For": "41.243.10.7", "X-Forwarded-Proto": "https", "X-Forwarded-Host": "ecole.example"}
    reponse = application.test_client().get("/_qui", headers=en_tetes)
    assert vus == {"adresse": "41.243.10.7", "https": True, "hote": "ecole.example"}
    assert "Strict-Transport-Security" in reponse.headers


def test_sans_serveur_web_les_en_tetes_transmis_sont_ignores(app):
    from flask import request
    vus = {}

    @app.route("/_qui")
    def qui():
        vus.update(adresse=request.remote_addr, https=request.is_secure)
        return "ok"

    app.test_client().get("/_qui", headers={"X-Forwarded-For": "41.243.10.7", "X-Forwarded-Proto": "https"})
    assert vus == {"adresse": "127.0.0.1", "https": False}


def test_sauvegarde_planifiee_une_archive_par_ecole(app, db, creer_classe, creer_eleve, tmp_path):
    from app.models.classe import Classe
    from app.models.ecole import Ecole
    from app.models.eleve import Eleve

    creer_eleve("Awa de la Une", creer_classe(), matricule="ET26-CP1-001")
    db.session.add(Ecole(id=2, nom="École Deux", sigle="ED", prefixe_matricule="ED26", actif=True))
    db.session.commit()
    classe2 = Classe(nom="CP1", niveau=1, annee_scolaire=Eleve.annee_scolaire_courante(), ecole_id=2)
    db.session.add(classe2)
    db.session.flush()
    db.session.add(Eleve(matricule="ED26-CP1-001", nom_complet="Ben de la Deux", classe_id=classe2.id, ecole_id=2))
    db.session.commit()

    for _ in range(2):  # deux passages : on ne garde qu'une archive par école
        resultat = app.test_cli_runner().invoke(args=["sauvegarder-ecoles", "--dossier", str(tmp_path), "--garder", "1"])
        assert resultat.exit_code == 0, resultat.output

    fichiers = sorted(os.listdir(tmp_path))
    assert len(fichiers) == 2 and fichiers[0].startswith("ecole1_sauvegarde_et_") and fichiers[1].startswith("ecole2_sauvegarde_ed_")
    contenus = {}
    for nom in fichiers:
        with zipfile.ZipFile(tmp_path / nom) as archive:
            donnees = json.loads(archive.read("donnees.json"))
            contenus[nom[:6]] = ([e["nom_complet"] for e in donnees["tables"]["eleves"]], archive.read("eleves.csv").decode())
    assert contenus["ecole1"][0] == ["Awa de la Une"] and "Ben" not in contenus["ecole1"][1]
    assert contenus["ecole2"][0] == ["Ben de la Deux"] and "Awa" not in contenus["ecole2"][1]
