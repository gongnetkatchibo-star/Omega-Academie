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


# --------------------------------------------------------------- lot 2 : argent
def _payer(client, eleve, montant, echeance="inscription", **extra):
    donnees = {"echeance": echeance, "montant": str(montant), "mode": "especes"}
    donnees.update(extra)
    return client.post(f"/finances/{eleve.id}", data=donnees, follow_redirects=True)


def test_caisse_refuse_montants_negatifs_decimaux_ou_absurdes(client, db, creer_utilisateur):
    from datetime import date
    from app.models.mouvement_caisse import MouvementCaisse

    creer_utilisateur("Compt", "c@t.td", "comptable")
    connecter(client, "c@t.td")
    for recette in ("-50000", "12.5", "nan", "inf"):
        client.post("/caisse/nouveau", data={"type": "Divers", "libelle": "x", "recette": recette, "depense": "",
                                            "date": date.today().isoformat()})
    assert MouvementCaisse.query.count() == 0
    r = client.post("/caisse/nouveau", data={"type": "Salaire", "libelle": "x", "depense": "1000", "recette": "",
                                             "date": date.today().isoformat()}, follow_redirects=True)
    assert "type de mouvement" in _texte(r)  # un salaire passe par le module Salaires


def test_trop_percu_refuse(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.paiement import Paiement

    creer_utilisateur("Compt", "c@t.td", "comptable")
    eleve = creer_eleve("Awa", creer_classe(frais_inscription=50000))
    connecter(client, "c@t.td")
    assert "dépasse ce qui reste dû" in _texte(_payer(client, eleve, 500000))
    _payer(client, eleve, 30000)
    assert "dépasse" in _texte(_payer(client, eleve, 30000))
    _payer(client, eleve, 20000)
    assert "déjà entièrement payée" in _texte(_payer(client, eleve, 1000))
    assert sum(p.montant for p in Paiement.query.all()) == 50000


def test_cloture_de_caisse(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from datetime import date, timedelta
    from app.models.mouvement_caisse import MouvementCaisse

    creer_utilisateur("Fond", "f@t.td", "fondateur")
    connecter(client, "f@t.td")
    hier = (date.today() - timedelta(days=1)).isoformat()
    client.post("/caisse/nouveau", data={"type": "Divers", "libelle": "Achat", "depense": "1000", "recette": "", "date": hier})
    mouvement = MouvementCaisse.query.one()
    client.post("/caisse/cloture", data={"date_cloture": hier})
    r = client.post(f"/caisse/mouvement/{mouvement.id}/modifier", data={"type": "Divers", "libelle": "Truqué", "depense": "10",
                                                                         "recette": "", "date": hier}, follow_redirects=True)
    assert "clôturée" in _texte(r)
    r = client.post("/caisse/nouveau", data={"type": "Divers", "libelle": "Oubli", "depense": "500", "recette": "", "date": hier},
                    follow_redirects=True)
    assert "clôturée" in _texte(r)
    db.session.remove()
    assert MouvementCaisse.query.one().libelle == "Achat"
    r = client.post("/caisse/cloture", data={"date_cloture": (date.today() + timedelta(days=3)).isoformat()}, follow_redirects=True)
    assert "futur" in _texte(r)


def test_recu_d_un_paiement_annule_signale_a_la_verification(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.mouvement_caisse import MouvementCaisse
    from app.models.document_verifiable import DocumentVerifiable
    from app.models.paiement import Paiement

    creer_utilisateur("Fond", "f@t.td", "fondateur")
    eleve = creer_eleve("Awa", creer_classe(frais_inscription=50000))
    connecter(client, "f@t.td")
    _payer(client, eleve, 50000)
    mouvement_id = MouvementCaisse.query.one().id
    assert client.get(f"/caisse/recu/{mouvement_id}/pdf").status_code == 200
    code = DocumentVerifiable.query.one().code
    client.post(f"/finances/paiement/{Paiement.query.one().id}/supprimer")
    db.session.remove()
    assert DocumentVerifiable.query.one().annule
    from flask import g
    g.pop("_login_user", None)
    assert client.get(f"/caisse/recu/{mouvement_id}/pdf").status_code == 302
    assert code


def test_salaire_paye_une_seule_fois_et_annule_avec_trace(client, db, creer_utilisateur):
    from app.models.mouvement_caisse import MouvementCaisse
    from app.models.salaire import Salaire
    from app.services.temps import maintenant

    creer_utilisateur("Fond", "f@t.td", "fondateur")
    prof = creer_utilisateur("Prof", "p@t.td", "enseignant")
    connecter(client, "f@t.td")
    r = client.post("/salaires/nouveau", data={"personnel_id": prof.id, "mois": "9", "annee": "1990", "montant": "100000"},
                    follow_redirects=True)
    assert "L'année du salaire" in _texte(r)
    client.post("/salaires/nouveau", data={"personnel_id": prof.id, "mois": "9", "annee": str(maintenant().year), "montant": "100000"})
    salaire = Salaire.query.one()
    client.post(f"/salaires/{salaire.id}/payer")
    client.post(f"/salaires/{salaire.id}/payer")
    assert MouvementCaisse.query.count() == 1
    client.post(f"/salaires/{salaire.id}/supprimer")
    lignes = MouvementCaisse.query.all()
    assert len(lignes) == 2 and sum(float(l.recette) - float(l.depense) for l in lignes) == 0


def test_arriere_de_l_annee_precedente(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.eleve import Eleve
    from app.models.historique import HistoriqueScolaire
    from app.models.paiement import Paiement

    creer_utilisateur("Compt", "c@t.td", "comptable")
    debut = int(Eleve.annee_scolaire_courante()[:4])
    passee = f"{debut - 1}-{debut}"
    ancienne = creer_classe("CE2", 4, annee=passee, frais_inscription=20000)
    eleve = creer_eleve("Awa", creer_classe("CM1", 5, frais_inscription=30000))
    db.session.add(HistoriqueScolaire(eleve_id=eleve.id, classe_id=ancienne.id, annee_scolaire=passee, resultat="admis"))
    db.session.commit()
    connecter(client, "c@t.td")
    page = _texte(client.get(f"/finances/{eleve.id}"))
    assert f"Arriéré {passee}" in page
    _payer(client, eleve, 20000, annee=passee)
    paiement = Paiement.query.one()
    assert paiement.annee_scolaire == passee
    assert f"Arriéré {passee}" not in _texte(client.get(f"/finances/{eleve.id}"))
    # Une année qui n'est pas un arriéré : refusée.
    assert "montant valide" in _texte(_payer(client, eleve, 1000, annee="2001-2002"))


# ------------------------------------------------------- lot 4 : modules
def test_notes_cloturees_par_la_direction(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.enseignant import Enseignant, Affectation
    from app.models.evaluation import Evaluation
    from app.models.note import Note
    from app.services.periodes import periodes

    creer_utilisateur("Fond", "f@t.td", "fondateur")
    prof = creer_utilisateur("Prof", "p@t.td", "enseignant")
    classe = creer_classe("CM1", 4)
    eleve = creer_eleve("Awa", classe)
    profil = Enseignant(user_id=prof.id)
    db.session.add(profil)
    db.session.flush()
    db.session.add(Affectation(enseignant_id=profil.id, classe_id=classe.id, matiere="Français"))
    db.session.commit()
    connecter(client, "p@t.td")
    from datetime import date
    with client.application.test_request_context():
        from flask import g
        g.ecole_id = 1
        periode = periodes()[0]
    client.post(f"/notes/classe/{classe.id}", data={"matiere": "Français", "trimestre": periode, "titre": "Dictée",
                                                  "type": "devoir", "coefficient": "1", "date": date.today().isoformat()})
    evaluation = Evaluation.query.one()
    client.post(f"/notes/evaluation/{evaluation.id}", data={f"note_{eleve.id}": "7"})
    client.post("/auth/deconnexion")
    from flask import g
    g.pop("_login_user", None)
    connecter(client, "f@t.td")
    client.post("/notes/cloture", data={"periode": periode})
    client.post("/auth/deconnexion")
    g.pop("_login_user", None)
    connecter(client, "p@t.td")
    r = client.post(f"/notes/evaluation/{evaluation.id}", data={f"note_{eleve.id}": "10"}, follow_redirects=True)
    assert "clôturées" in _texte(r)
    assert client.post(f"/notes/evaluation/{evaluation.id}/supprimer").status_code == 302
    db.session.remove()
    assert Note.query.one().valeur == 7 and Evaluation.query.count() == 1


def test_emploi_du_temps_modifier_retirer_et_annees(client, db, creer_utilisateur, creer_classe):
    from app.models.emploi_du_temps import Creneau
    from app.models.eleve import Eleve

    creer_utilisateur("Fond", "f@t.td", "fondateur")
    debut = int(Eleve.annee_scolaire_courante()[:4])
    ancienne = creer_classe("CE1", 2, annee=f"{debut - 1}-{debut}")
    classe = creer_classe("CE1", 2)
    db.session.add(Creneau(classe_id=ancienne.id, matiere="Français", jour="Lundi", heure_debut="08:00", heure_fin="09:00"))
    db.session.commit()
    connecter(client, "f@t.td")
    r = client.post(f"/emploi-du-temps/classe/{classe.id}", data={"matiere": "Français", "jour": "Lundi", "heure_debut": "08:00",
                                                                 "heure_fin": "09:00"}, follow_redirects=True)
    assert "Créneau ajouté" in _texte(r)  # le créneau de l'an dernier ne bloque plus
    r = client.post(f"/emploi-du-temps/classe/{classe.id}", data={"matiere": "Français", "jour": "Dimanche", "heure_debut": "08:00",
                                                                 "heure_fin": "09:00"}, follow_redirects=True)
    assert "Jour invalide" in _texte(r)
    creneau = Creneau.query.filter_by(classe_id=classe.id).one()
    client.post(f"/emploi-du-temps/creneau/{creneau.id}/modifier", data={"matiere": "Français", "jour": "Mardi",
                                                                       "heure_debut": "10:00", "heure_fin": "11:00"})
    assert db.session.get(Creneau, creneau.id).jour == "Mardi"
    client.post(f"/emploi-du-temps/creneau/{creneau.id}/supprimer")
    assert Creneau.query.filter_by(classe_id=classe.id).count() == 0


def test_secretariat_justifie_une_absence(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from datetime import date
    from app.models.absence import Absence

    creer_utilisateur("Sec", "s@t.td", "secretaire")
    classe = creer_classe("CM1", 4)
    eleve = creer_eleve("Awa", classe)
    absence = Absence(eleve_id=eleve.id, classe_id=classe.id, date=date.today(), justifiee=False)
    db.session.add(absence)
    db.session.commit()
    connecter(client, "s@t.td")
    client.post(f"/absences/{absence.id}/justifier", data={"justifiee": "1", "motif": "Mot du parent"})
    db.session.remove()
    a = Absence.query.one()
    assert a.justifiee and a.motif == "Mot du parent"


def test_resultat_du_test_met_a_jour_la_preinscription(client, db, creer_utilisateur, creer_classe):
    from datetime import date
    from app.models.preinscription import PreInscription
    from app.models.test_niveau import TestNiveau

    creer_utilisateur("Sec", "s@t.td", "secretaire")
    classe = creer_classe("CM1", 4)
    test = TestNiveau(nom_candidat="Candidat", classe_demandee_id=classe.id, date_test=date.today())
    db.session.add(test)
    db.session.flush()
    demande = PreInscription(nom_candidat="Candidat", nom_parent="Parent", telephone_parent="66000000",
                             classe_demandee_id=classe.id, statut="convoquee", test_niveau_id=test.id, reference="PRE-1")
    db.session.add(demande)
    db.session.commit()
    connecter(client, "s@t.td")
    client.post(f"/tests-niveau/{test.id}/decision", data={"note_obtenue": "3"})
    db.session.remove()
    assert PreInscription.query.one().statut == "non_admise"


def test_annonce_d_une_classe_invisible_des_autres_familles(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.annonce import Annonce

    creer_utilisateur("Sec", "s@t.td", "secretaire")
    p1 = creer_utilisateur("Parent CM1", "p1@t.td", "parent")
    p2 = creer_utilisateur("Parent CM2", "p2@t.td", "parent")
    cm1, cm2 = creer_classe("CM1", 4), creer_classe("CM2", 5)
    e1, e2 = creer_eleve("Un", cm1), creer_eleve("Deux", cm2)
    e1.parents.append(p1)
    e2.parents.append(p2)
    db.session.commit()
    connecter(client, "s@t.td")
    client.post("/communication/nouvelle", data={"titre": "Sortie du CM1", "contenu": "x", "destinataire": "parent",
                                                "classe_id": str(cm1.id)}, content_type="multipart/form-data")
    annonce = Annonce.query.one()
    assert annonce.classe_id == cm1.id
    client.post("/auth/deconnexion")
    from flask import g
    g.pop("_login_user", None)
    connecter(client, "p1@t.td")
    assert "Sortie du CM1" in _texte(client.get("/"))  # sur le tableau de bord de la famille
    client.post("/auth/deconnexion")
    g.pop("_login_user", None)
    connecter(client, "p2@t.td")
    assert "Sortie du CM1" not in _texte(client.get("/communication/"))
    assert client.get(f"/communication/{annonce.id}").status_code == 403
