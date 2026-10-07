"""Fiabilité des données : emails groupés, numéros de reçu, matricules,
moyenne unique, taux de recouvrement, contenus lourds hors des listes."""

from sqlalchemy import inspect


def test_email_groupe_un_exemplaire_par_destinataire(app, monkeypatch):
    from app.extensions import envoyer_email
    from app.models.journal_email import JournalEmail

    envois = []

    class Reponse:
        status_code = 201

    monkeypatch.setattr("requests.post", lambda url, **k: envois.append(k["json"]) or Reponse())
    app.config["BREVO_API_KEY"] = "cle-test"

    assert envoyer_email(["a@test.com", "b@test.com", "a@test.com", None], "Annonce", "Bonjour <tous>") is True
    message = envois[0]
    assert "to" not in message  # personne ne voit l'adresse des autres
    assert message["messageVersions"] == [{"to": [{"email": "a@test.com"}]}, {"to": [{"email": "b@test.com"}]}]
    assert message["htmlContent"] == "Bonjour &lt;tous&gt;"

    assert envoyer_email(["seul@test.com"], "Reçu", "Merci") is True
    assert envois[1]["to"] == [{"email": "seul@test.com"}] and "messageVersions" not in envois[1]
    assert JournalEmail.query.count() == 2


def test_email_groupe_decoupe_en_lots_et_journal_tronque(app, monkeypatch):
    from app import extensions
    from app.models.journal_email import JournalEmail

    envois = []

    class Reponse:
        status_code = 201

    monkeypatch.setattr("requests.post", lambda url, **k: envois.append(k["json"]) or Reponse())
    monkeypatch.setattr(extensions, "LOT_EMAILS", 40)
    app.config["BREVO_API_KEY"] = "cle-test"

    adresses = [f"parent{i:03d}@test.com" for i in range(100)]
    assert extensions.envoyer_email(adresses, "Annonce", "Texte") is True
    assert [len(m["messageVersions"]) for m in envois] == [40, 40, 20]
    ligne = JournalEmail.query.one()
    assert len(ligne.destinataires) <= 500 and ligne.destinataires.startswith("100 destinataires")


def test_numero_de_recu_jamais_reattribue(app, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.mouvement_caisse import MouvementCaisse
    from app.models.paiement import Paiement
    from app.services.paiements import enregistrer_paiement

    comptable = creer_utilisateur("Compt", "compt@test.com", "comptable")
    eleve = creer_eleve("Awa", creer_classe(frais_inscription=30000))

    premier = enregistrer_paiement(eleve, 5000, "especes", "inscription", comptable)
    deuxieme = enregistrer_paiement(eleve, 5000, "especes", "inscription", comptable)
    MouvementCaisse.query.filter_by(origine_id=premier.id).delete()
    db.session.delete(premier)
    db.session.commit()
    troisieme = enregistrer_paiement(eleve, 5000, "especes", "inscription", comptable)

    assert deuxieme.numero_recu.endswith("-00002") and troisieme.numero_recu.endswith("-00003")
    numeros = [p.numero_recu for p in Paiement.query.all()]
    assert len(numeros) == len(set(numeros)) == 2


def test_numero_de_recu_reprend_apres_les_recus_existants(app, db, creer_utilisateur, creer_classe, creer_eleve):
    """Base déjà en service avant le compteur : on continue après le plus
    grand numéro existant."""
    from app.models.eleve import Eleve
    from app.models.paiement import Paiement
    from app.services.paiements import enregistrer_paiement
    from app.services.temps import maintenant

    comptable = creer_utilisateur("Compt", "compt@test.com", "comptable")
    eleve = creer_eleve("Awa", creer_classe(frais_inscription=30000))
    db.session.add(Paiement(
        eleve_id=eleve.id, montant=1000, numero_recu=f"REC-{maintenant().year}-00007",
        annee_scolaire=Eleve.annee_scolaire_courante(),
    ))
    db.session.commit()

    assert enregistrer_paiement(eleve, 5000, "especes", "inscription", comptable).numero_recu.endswith("-00008")


def test_matricule_jamais_reattribue_apres_changement_de_classe(app, db, creer_classe):
    from flask import g
    from app.models.eleve import Eleve

    g.ecole_id = 1  # comme dans une requête : le préfixe est celui de l'école
    cp1, cp2 = creer_classe(nom="CP1", niveau=1), creer_classe(nom="CP2", niveau=2)
    eleves = []
    for nom in ("Awa", "Ben"):
        eleve = Eleve(matricule=Eleve.generer_matricule(cp1), nom_complet=nom, classe_id=cp1.id)
        db.session.add(eleve)
        db.session.commit()
        eleves.append(eleve)
    assert [e.matricule for e in eleves] == ["ET26-CP1-001", "ET26-CP1-002"]

    eleves[0].classe_id = cp2.id  # Awa change de classe : il ne reste qu'un élève en CP1
    db.session.commit()
    assert Eleve.generer_matricule(cp1) == "ET26-CP1-003"
    assert Eleve.generer_matricule(cp2) == "ET26-CP2-001"


def _classe_notee(db, creer_classe, creer_eleve):
    from app.models.bulletin import CoefficientMatiere
    from app.models.evaluation import Evaluation
    from app.models.note import Note
    from app.services.temps import aujourd_hui

    classe = creer_classe(nom="6e", niveau=7)
    awa = creer_eleve("Awa", classe, matricule="ET26-6E-001")
    a = classe.annee_scolaire
    composition = Evaluation(classe_id=classe.id, matiere="Maths", trimestre="T1", annee_scolaire=a,
                             titre="Composition", type="composition", date=aujourd_hui(), coefficient=2)
    db.session.add(composition)
    db.session.flush()

    def note(matiere, valeur, trimestre, evaluation=None):
        return Note(eleve_id=awa.id, classe_id=classe.id, matiere=matiere, valeur=valeur, bareme=20,
                    trimestre=trimestre, annee_scolaire=a, evaluation_id=evaluation.id if evaluation else None)

    db.session.add_all([
        note("Maths", 18, "T1", composition), note("Maths", 6, "T1"),   # (18×2 + 6) / 3 = 14
        note("Français", 8, "T1"),
        note("Maths", 12, "T2"),
        CoefficientMatiere(classe_id=classe.id, matiere="Maths", coefficient=3),
    ])
    db.session.commit()
    return classe, awa


def test_moyenne_des_statistiques_identique_au_bulletin(app, db, creer_classe, creer_eleve):
    from app.services.bulletins import bulletins_de_la_classe
    from app.services.moyennes import a_reussi, moyenne_eleve
    from app.services.statistiques import stats_reussite

    classe, awa = _classe_notee(db, creer_classe, creer_eleve)
    annee = classe.annee_scolaire
    bulletin = bulletins_de_la_classe(classe, "AN", annee)["bulletins"][awa.id]

    # T1 : (14×3 + 8×1) / 4 = 12,5 ; T2 : 12 ; année : 12,25 (moyenne simple des 4 notes : 11).
    assert bulletin["moyenne"] == 12.25
    assert moyenne_eleve(awa, annee) == bulletin["moyenne"]
    assert a_reussi(awa, annee) is True
    assert stats_reussite([awa], annee)["moyenne_generale"] == 12.25


def test_moyenne_d_une_annee_passee_utilise_la_classe_de_cette_annee(app, db, creer_classe, creer_eleve):
    from app.models.note import Note
    from app.services.moyennes import a_reussi, moyenne_eleve

    cm2 = creer_classe(nom="CM2", niveau=6, annee="2025-2026")
    sixieme = creer_classe(nom="6e", niveau=7)
    eleve = creer_eleve("Ben", sixieme)  # aujourd'hui en 6e, noté l'an dernier en CM2 (sur 10)
    db.session.add(Note(eleve_id=eleve.id, classe_id=cm2.id, matiere="Maths", valeur=6, bareme=10,
                        trimestre="T1", annee_scolaire="2025-2026"))
    db.session.commit()

    assert moyenne_eleve(eleve, "2025-2026") == 6     # reste sur 10, pas converti sur 20
    assert a_reussi(eleve, "2025-2026") is True       # seuil du primaire (5/10)
    assert moyenne_eleve(eleve, sixieme.annee_scolaire) is None


def test_recouvrement_tient_compte_des_remises_et_frais_annexes(app, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.frais_annexe import FraisAnnexe
    from app.services.paiements import enregistrer_paiement, resume_paiements
    from app.services.statistiques import stats_financieres

    comptable = creer_utilisateur("Compt", "compt@test.com", "comptable")
    classe = creer_classe(frais_inscription=10000)
    boursier, autre = creer_eleve("Awa", classe, matricule="M1"), creer_eleve("Ben", classe, matricule="M2")
    boursier.remise_pourcent = 50
    tenue = FraisAnnexe(libelle="Tenue", montant=2000, annee_scolaire=classe.annee_scolaire)
    db.session.add(tenue)
    db.session.commit()

    enregistrer_paiement(boursier, 5000, "especes", "inscription", comptable)
    enregistrer_paiement(boursier, 2000, "especes", "annexe", comptable, frais_annexe=tenue)

    seul = stats_financieres([boursier], classe.annee_scolaire)
    assert (seul["total_a_recouvrer"], seul["total_encaisse"], seul["solde_a_recouvrer"]) == (7000, 7000, 0)
    assert seul["taux_recouvrement"] == 100
    assert seul["solde_a_recouvrer"] == resume_paiements(boursier)["solde"]

    tous = stats_financieres([boursier, autre], classe.annee_scolaire)
    assert (tous["total_a_recouvrer"], tous["solde_a_recouvrer"]) == (19000, 12000)
    assert round(tous["taux_recouvrement"], 1) == 36.8


def test_photos_et_fichiers_ne_sont_pas_charges_dans_les_listes(app, db, creer_classe, creer_eleve):
    from app.models.eleve import Eleve
    from app.models.ressource import Ressource

    eleve = creer_eleve("Awa", creer_classe())
    eleve.photo, eleve.photo_mime = b"image", "image/png"
    db.session.add(Ressource(titre="Livre", nom_fichier="livre.pdf", contenu=b"pdf", type_mime="application/pdf"))
    db.session.commit()
    db.session.expire_all()

    eleve, ressource = Eleve.query.first(), Ressource.query.first()
    assert "photo" in inspect(eleve).unloaded and "contenu" in inspect(ressource).unloaded
    assert eleve.photo == b"image" and ressource.contenu == b"pdf"  # chargés à la demande
