"""Tests sur Finances/Caisse — la partie la plus critique côté argent :
un paiement doit toujours créer sa ligne de Caisse, jamais la dupliquer,
et rester corrigible/supprimable seulement par les bons rôles."""

from tests.conftest import connecter


def test_paiement_cree_une_ligne_de_caisse_automatique(client, creer_utilisateur, creer_classe, creer_eleve, db):
    from app.models.mouvement_caisse import MouvementCaisse

    creer_utilisateur("Compt", "compt@test.com", "comptable")
    classe = creer_classe(frais_inscription=15000, frais_tranche1=10000, frais_tranche2=5000)
    eleve = creer_eleve("Eleve Test", classe)

    connecter(client, "compt@test.com")
    r = client.post(f"/finances/{eleve.id}", data={"echeance": "inscription", "montant": "15000", "mode": "especes"}, follow_redirects=True)
    assert r.status_code == 200

    mouvements = MouvementCaisse.query.all()
    assert len(mouvements) == 1
    assert mouvements[0].automatique is True
    assert mouvements[0].recette == 15000
    assert mouvements[0].eleve_id == eleve.id


def test_correction_paiement_met_a_jour_la_caisse(client, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.paiement import Paiement
    from app.models.mouvement_caisse import MouvementCaisse

    creer_utilisateur("Compt", "compt@test.com", "comptable")
    classe = creer_classe(frais_inscription=15000)
    eleve = creer_eleve("Eleve Test", classe)

    connecter(client, "compt@test.com")
    client.post(f"/finances/{eleve.id}", data={"echeance": "inscription", "montant": "15000", "mode": "especes"})
    paiement = Paiement.query.first()

    client.post(f"/finances/paiement/{paiement.id}/modifier", data={"echeance": "inscription", "montant": "12000", "mode": "mobile_money"})

    mouvement = MouvementCaisse.query.filter_by(origine_id=paiement.id).first()
    assert mouvement.recette == 12000


def test_comptable_ne_peut_pas_supprimer_un_paiement(client, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.paiement import Paiement

    creer_utilisateur("Compt", "compt@test.com", "comptable")
    classe = creer_classe(frais_inscription=15000)
    eleve = creer_eleve("Eleve Test", classe)

    connecter(client, "compt@test.com")
    client.post(f"/finances/{eleve.id}", data={"echeance": "inscription", "montant": "15000", "mode": "especes"})
    paiement = Paiement.query.first()

    r = client.post(f"/finances/paiement/{paiement.id}/supprimer")
    assert r.status_code == 403
    assert Paiement.query.count() == 1


def test_fondateur_peut_supprimer_un_paiement_et_sa_ligne_de_caisse(client, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.paiement import Paiement
    from app.models.mouvement_caisse import MouvementCaisse

    creer_utilisateur("Fond", "fond@test.com", "fondateur")
    classe = creer_classe(frais_inscription=15000)
    eleve = creer_eleve("Eleve Test", classe)

    connecter(client, "fond@test.com")
    client.post(f"/finances/{eleve.id}", data={"echeance": "inscription", "montant": "15000", "mode": "especes"})
    paiement = Paiement.query.first()

    client.post(f"/finances/paiement/{paiement.id}/supprimer", follow_redirects=True)
    assert Paiement.query.count() == 0
    assert MouvementCaisse.query.count() == 0


def test_salaire_capture_fonction_et_contact(client, creer_utilisateur):
    from app.models.salaire import Salaire

    creer_utilisateur("Compt", "compt@test.com", "comptable")
    prof = creer_utilisateur("Awa Mbaye", "awa@test.com", "enseignant")
    connecter(client, "compt@test.com")

    client.post("/salaires/nouveau", data={
        "personnel_id": prof.id, "fonction": "Enseignante CP1", "mois": "9", "annee": "2026",
        "montant": "150000", "email_contact": "awa.perso@test.com",
    })
    salaire = Salaire.query.first()
    assert salaire.fonction == "Enseignante CP1"
    assert salaire.email_contact == "awa.perso@test.com"


def test_page_salaire_propose_donnees_pour_auto_remplissage(client, creer_utilisateur):
    creer_utilisateur("Compt", "compt@test.com", "comptable")
    creer_utilisateur("Awa Mbaye", "awa@test.com", "enseignant")
    connecter(client, "compt@test.com")

    html = client.get("/salaires/nouveau").data.decode()
    assert 'data-email="awa@test.com"' in html


def test_marquer_paye_envoie_un_email_au_beneficiaire(client, creer_utilisateur, monkeypatch):
    from app.models.salaire import Salaire
    from app.models.journal_email import JournalEmail
    import app.services.notifications as notifications_module

    appels = []
    monkeypatch.setattr(notifications_module, "envoyer_email", lambda dest, sujet, corps: appels.append((dest, sujet)) or True)

    creer_utilisateur("Compt", "compt@test.com", "comptable")
    prof = creer_utilisateur("Prof", "prof@test.com", "enseignant")
    connecter(client, "compt@test.com")

    client.post("/salaires/nouveau", data={
        "personnel_id": prof.id, "mois": "9", "annee": "2026", "montant": "100000",
        "email_contact": "prof.perso@test.com",
    })
    salaire = Salaire.query.first()
    client.post(f"/salaires/{salaire.id}/payer")

    assert appels == [(["prof.perso@test.com"], "Salaire versé — Septembre 2026")]


def test_journal_salaires_filtrable_par_nom_et_periode(client, creer_utilisateur, db):
    from app.models.salaire import Salaire
    from datetime import date

    creer_utilisateur("Compt", "compt@test.com", "comptable")
    awa = creer_utilisateur("Awa Mbaye", "awa@test.com", "enseignant")
    ali = creer_utilisateur("Ali Hassan", "ali@test.com", "enseignant")
    db.session.add(Salaire(personnel_id=awa.id, mois=9, annee=2026, montant=100000, statut="paye", date_paiement=date(2026, 9, 5)))
    db.session.add(Salaire(personnel_id=ali.id, mois=9, annee=2026, montant=90000, statut="paye", date_paiement=date(2026, 9, 20)))
    db.session.commit()

    connecter(client, "compt@test.com")

    html = client.get("/salaires/?nom=Awa").data.decode()
    assert "Awa Mbaye" in html and "Ali Hassan" not in html

    html = client.get("/salaires/?date_debut=2026-09-01&date_fin=2026-09-10").data.decode()
    assert "Awa Mbaye" in html and "Ali Hassan" not in html


def test_journal_salaires_exportable_pdf_excel_csv(client, creer_utilisateur, db):
    from app.models.salaire import Salaire

    creer_utilisateur("Compt", "compt@test.com", "comptable")
    prof = creer_utilisateur("Prof Test", "prof@test.com", "enseignant")
    db.session.add(Salaire(personnel_id=prof.id, mois=9, annee=2026, montant=100000, statut="paye"))
    db.session.commit()

    connecter(client, "compt@test.com")
    for fmt in ["csv", "xlsx", "pdf"]:
        r = client.get(f"/salaires/export/{fmt}")
        assert r.status_code == 200
        assert len(r.data) > 0
