"""Audit complet d'octobre 2026 : chaque faille trouvée a son test."""

from datetime import date, timedelta

from tests.conftest import connecter


def _texte(r):
    return r.get_data(as_text=True)


def _accorder(db, role, module, autorise=True, ecole_id=1):
    from app.models.permission import Permission
    from app.services.permissions import vider_cache

    db.session.add(Permission(ecole_id=ecole_id, role=role, module=module, autorise=autorise))
    db.session.commit()
    vider_cache()


# ------------------------------------------------------------ rôles des comptes
def test_attribution_des_roles_limitee_au_rang(client, db, creer_utilisateur):
    from app.models.user import User

    fondateur = creer_utilisateur("Fond", "f@t.td", "fondateur")
    ag = creer_utilisateur("AG", "ag@t.td", "administrateur_general")
    prof = creer_utilisateur("Prof", "p@t.td", "enseignant")
    _accorder(db, "administrateur_general", "gestion_roles")
    _accorder(db, "fondateur", "gestion_roles")
    ids = {"f": fondateur.id, "ag": ag.id, "p": prof.id}

    connecter(client, "ag@t.td")
    # L'administrateur général ne rétrograde ni ne verrouille le fondateur…
    client.post(f"/developpeur/utilisateur/{ids['f']}", data={"role": "eleve", "statut": "verrouille"})
    # … et ne fabrique pas un fondateur.
    client.post(f"/developpeur/utilisateur/{ids['p']}", data={"role": "fondateur", "statut": "actif"})
    assert db.session.get(User, ids["f"]).role == "fondateur" and db.session.get(User, ids["f"]).statut == "actif"
    assert db.session.get(User, ids["p"]).role == "enseignant"
    # Un rôle sous le sien : permis.
    client.post(f"/developpeur/utilisateur/{ids['p']}", data={"role": "secretaire", "statut": "actif"})
    assert db.session.get(User, ids["p"]).role == "secretaire"

    client.post("/auth/deconnexion")
    connecter(client, "f@t.td")
    client.post(f"/developpeur/utilisateur/{ids['p']}", data={"role": "super_administrateur", "statut": "actif"})
    assert db.session.get(User, ids["p"]).role == "secretaire"
    page = _texte(client.get("/developpeur/"))
    assert 'value="fondateur"' not in page and 'value="super_administrateur"' not in page


# --------------------------------------------------------------------- frais
def test_creer_une_classe_ne_change_pas_les_frais(client, db, creer_utilisateur, creer_classe):
    from app.models.classe import Classe
    from app.models.eleve import Eleve

    annee = Eleve.annee_scolaire_courante()
    cp1 = creer_classe("CP1", 1, annee=annee, frais_inscription=10000, frais_tranche1=20000, frais_tranche2=30000)
    creer_utilisateur("Sec", "s@t.td", "secretaire")
    connecter(client, "s@t.td")
    assert "frais_tranche1" not in _texte(client.get("/classes/nouvelle"))
    client.post("/classes/nouvelle", data={"nom": "CP2", "niveau": "2", "annee_scolaire": annee,
                                          "frais_inscription": "0", "frais_tranche1": "", "frais_tranche1_autre": "1",
                                          "frais_tranche2": "", "frais_tranche2_autre": "1"})
    cp2 = Classe.query.filter_by(nom="CP2").one()
    db.session.refresh(cp1)
    assert (cp1.frais_tranche1, cp1.frais_tranche2) == (20000, 30000)
    assert (cp2.frais_inscription, cp2.frais_tranche1, cp2.frais_tranche2) == (10000, 20000, 30000)


# ------------------------------------------------------------- comptes élèves
def test_compte_eleve_refuse_libere_le_matricule(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.eleve import Eleve
    from app.models.user import User

    eleve = creer_eleve("Moussa", creer_classe("CM1", 4), matricule="ET26-CM1-009")
    eleve.date_naissance = date(2014, 5, 20)
    db.session.commit()
    eleve_id = eleve.id
    donnees = {"role": "eleve", "ecole_id": "1", "matricule": "ET26-CM1-009", "date_naissance_eleve": "2014-05-20",
               "mot_de_passe": "eleve12345", "confirmation": "eleve12345"}
    client.post("/auth/inscription", data=donnees)  # un camarade prend le matricule
    usurpateur = User.query.filter_by(role="eleve").one()

    creer_utilisateur("Sec", "s@t.td", "secretaire")
    connecter(client, "s@t.td")
    client.post(f"/secretariat/demandes/{usurpateur.id}/refuser")
    assert db.session.get(Eleve, eleve_id).user_id is None
    client.post("/auth/deconnexion")

    r = client.post("/auth/inscription", data=donnees, follow_redirects=True)
    assert "activé après vérification" in _texte(r)
    assert db.session.get(Eleve, eleve_id).user_id not in (None, usurpateur.id)


# ------------------------------------------------------------------ annonces
def test_email_d_annonce_de_classe_seulement_a_ceux_qui_peuvent_la_lire(client, db, monkeypatch, creer_utilisateur,
                                                                        creer_classe, creer_eleve):
    envois = []
    monkeypatch.setattr("app.services.notifications.envoyer_email", lambda d, s, c, **k: envois.append(list(d)) or True)
    cp1, cm1 = creer_classe("CP1", 1), creer_classe("CM1", 4)
    comptable = creer_utilisateur("Compta", "c@t.td", "comptable")
    parent_cp1 = creer_utilisateur("Parent", "p@t.td", "parent")
    enfant_compta, enfant_cp1 = creer_eleve("Ali compta", cm1), creer_eleve("Bob CP1", cp1)
    enfant_compta.parents.append(comptable)
    enfant_cp1.parents.append(parent_cp1)
    creer_utilisateur("Sec", "s@t.td", "secretaire")
    db.session.commit()
    connecter(client, "s@t.td")
    client.post("/communication/nouvelle", data={"titre": "Sortie", "contenu": "CP1 seulement", "destinataire": "parent",
                                                 "classe_id": cp1.id})
    destinataires = envois[-1]
    assert "p@t.td" in destinataires and "c@t.td" not in destinataires


# --------------------------------------------------------------------- notes
def test_coefficients_et_appreciations_fixes_apres_cloture(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.bulletin import AppreciationBulletin, CoefficientMatiere, PeriodeCloturee
    from app.models.eleve import Eleve

    classe = creer_classe("CM1", 4)
    eleve = creer_eleve("Awa", classe)
    creer_utilisateur("Fond", "f@t.td", "fondateur")
    db.session.add(PeriodeCloturee(annee_scolaire=Eleve.annee_scolaire_courante(), periode="T1"))
    db.session.commit()
    connecter(client, "f@t.td")
    r = client.post(f"/notes/classe/{classe.id}/coefficients", data={"coefficient_0": "5"}, follow_redirects=True)
    assert "clôturées" in _texte(r) and CoefficientMatiere.query.count() == 0
    client.post(f"/notes/bulletin/{eleve.id}/appreciation", data={"trimestre": "T1", "appreciation": "Retouchée"})
    assert AppreciationBulletin.query.count() == 0


# -------------------------------------------------------------------- argent
def test_comptable_ne_se_paie_pas_lui_meme(client, db, creer_utilisateur):
    from app.models.salaire import Salaire
    from app.services.temps import maintenant

    compta = creer_utilisateur("Compta", "c@t.td", "comptable")
    creer_utilisateur("Fond", "f@t.td", "fondateur")
    compta_id = compta.id
    connecter(client, "c@t.td")
    r = client.post("/salaires/nouveau", data={"personnel_id": compta_id, "mois": "9", "annee": str(maintenant().year),
                                              "montant": "100000"}, follow_redirects=True)
    assert "Ton propre salaire" in _texte(r) and Salaire.query.count() == 0

    db.session.add(Salaire(personnel_id=compta_id, mois=9, annee=maintenant().year, montant=100000))
    db.session.commit()
    salaire_id = Salaire.query.one().id
    client.post(f"/salaires/{salaire_id}/payer")
    assert db.session.get(Salaire, salaire_id).statut == "impaye"
    client.post("/auth/deconnexion")
    connecter(client, "f@t.td")
    client.post(f"/salaires/{salaire_id}/payer")
    assert db.session.get(Salaire, salaire_id).statut == "paye"


def test_comptable_ne_corrige_que_les_paiements_du_jour(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.paiement import Paiement
    from app.services.temps import maintenant

    eleve = creer_eleve("Awa", creer_classe("CM1", 4, frais_inscription=50000))
    creer_utilisateur("Compta", "c@t.td", "comptable")
    connecter(client, "c@t.td")
    client.post(f"/finances/{eleve.id}", data={"echeance": "inscription", "montant": "20000", "mode": "especes"})
    paiement = Paiement.query.one()
    paiement.date_paiement = maintenant() - timedelta(days=3)
    db.session.commit()
    paiement_id = paiement.id
    r = client.post(f"/finances/paiement/{paiement_id}/modifier",
                    data={"echeance": "inscription", "montant": "2000", "mode": "especes"}, follow_redirects=True)
    assert "seule la direction" in _texte(r)
    assert db.session.get(Paiement, paiement_id).montant == 20000


# --------------------------------------------------------------- restauration
def test_restauration_n_accepte_ni_style_ni_type_actif(app, db):
    from app.models.ecole import Ecole
    from app.services.sauvegarde import exporter_ecole, restaurer_ecole

    ecole = db.session.get(Ecole, 1)
    donnees = exporter_ecole(ecole)
    donnees["reglages_ecole"]["couleur_theme"] = "red}</style><script>alert(1)</script>"
    donnees["reglages_ecole"]["logo_mime"] = "text/html"
    restaurer_ecole(ecole, donnees)
    db.session.commit()
    assert ecole.couleur_theme is None and ecole.logo_mime is None


# ------------------------------------------------------------ téléchargements
def test_export_avec_nom_de_classe_non_latin(client, db, creer_utilisateur, creer_classe, creer_eleve):
    classe = creer_classe("الصف 1", 1)
    creer_eleve("Awa", classe)
    creer_utilisateur("Sec", "s@t.td", "secretaire")
    connecter(client, "s@t.td")
    for fmt in ("csv", "xlsx"):
        r = client.get(f"/eleves/export/{fmt}?classe_id={classe.id}")
        assert r.status_code == 200
        entete = r.headers["Content-Disposition"]
        assert entete.startswith("attachment; filename=") and "filename*=UTF-8''" in entete


def test_pagination_ignore_les_parametres_techniques(client, db, creer_utilisateur, creer_classe):
    from app.models.eleve import Eleve

    classe = creer_classe("CM1", 4)
    db.session.add_all([Eleve(matricule=f"ET26-X-{i:03d}", nom_complet=f"Élève {i}", classe_id=classe.id) for i in range(60)])
    db.session.commit()
    creer_utilisateur("Sec", "s@t.td", "secretaire")
    connecter(client, "s@t.td")
    page = _texte(client.get("/eleves/?_anchor=x%0Aalert(1)&_external=1"))
    assert "alert(1)" not in page and "http://localhost/eleves" not in page


# ----------------------------------------------------------------- assistant
def test_assistant_suit_la_matrice_des_permissions(client, db, creer_utilisateur):
    from app.services.assistant import REFUS

    creer_utilisateur("Compta", "c@t.td", "comptable")
    _accorder(db, "comptable", "finances", autorise=False)
    connecter(client, "c@t.td")
    r = client.post("/assistant/", data={"question": "Quel est le recouvrement ?"})
    assert REFUS.split(",")[0] in _texte(r).replace("&#39;", "'")


# ------------------------------------------------------------------ absences
def test_appel_d_une_annee_passee_refuse(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.absence import Absence
    from app.models.enseignant import Enseignant, Affectation

    classe = creer_classe("CM1", 4)
    eleve = creer_eleve("Awa", classe)
    prof = creer_utilisateur("Prof", "p@t.td", "enseignant")
    ens = Enseignant(user_id=prof.id)
    db.session.add(ens)
    db.session.flush()
    db.session.add(Affectation(enseignant_id=ens.id, classe_id=classe.id, matiere="Français"))
    db.session.commit()
    connecter(client, "p@t.td")
    ancienne = (date.today() - timedelta(days=500)).isoformat()
    client.post(f"/absences/classe/{classe.id}", data={"date": ancienne, f"absent_{eleve.id}": "on"})
    assert all(a.date.isoformat() != ancienne for a in Absence.query.all())
