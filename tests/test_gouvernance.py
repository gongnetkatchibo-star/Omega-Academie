"""Gouvernance de la plateforme (audit oct. 2026, lot 3) : abonnements,
factures, stockage, assistance, annonces, journal, sauvegarde."""

import io
from datetime import date, timedelta

from tests.conftest import connecter


def _texte(r):
    return r.get_data(as_text=True)


def _oublier_utilisateur():
    from flask import g
    g.pop("_login_user", None)


def test_abonnement_facture_et_retard(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.ecole import Ecole
    from app.models.gouvernance import Facture

    creer_utilisateur("Dev", "dev@t.td", "developpeur")
    creer_utilisateur("Fond", "f@t.td", "fondateur")
    classe = creer_classe("CM2", 5)
    for i in range(3):
        creer_eleve(f"Élève {i}", classe, matricule=f"ET26-CM2-{i:03d}")
    connecter(client, "dev@t.td")
    debut = date.today() - timedelta(days=20)
    r = client.post("/plateforme/1/abonnement", data={
        "mode_facturation": "par_eleve", "tarif": "1500", "periodicite": "trimestriel", "nom_formule": "Standard",
        "date_echeance": debut.isoformat(), "quota_go": "5", "contact_nom": "M. Directeur", "contact_email": "dir@ecole.td",
    }, follow_redirects=True)
    assert "enregistrés" in _texte(r)
    assert "4500" in "".join(c for c in _texte(r) if c.isdigit() or c.isalpha())
    client.post("/plateforme/1/factures/emettre", data={"quantite": "3"})
    facture = Facture.query.one()
    assert facture.montant == 4500 and facture.numero.startswith("FAC-")
    assert db.session.get(Ecole, 1).date_echeance > debut
    pdf = client.get(f"/plateforme/facture/{facture.id}/pdf")
    assert pdf.mimetype == "application/pdf"

    # 20 jours de retard : la console propose de suspendre, rien n'est suspendu.
    facture.date_echeance = debut
    db.session.commit()
    assert "à suspendre" in _texte(client.get("/plateforme/"))
    assert db.session.get(Ecole, 1).actif
    client.post("/auth/deconnexion")
    _oublier_utilisateur()

    connecter(client, "f@t.td")
    page = _texte(client.get("/"))
    assert "Facture en retard de 20 jour" in page
    assert facture.numero in _texte(client.get("/etablissement/abonnement"))
    assert client.get(f"/etablissement/facture/{facture.id}/pdf").mimetype == "application/pdf"
    client.post("/auth/deconnexion")
    _oublier_utilisateur()

    connecter(client, "dev@t.td")
    client.post(f"/plateforme/facture/{facture.id}/payer", data={"date_paiement": date.today().isoformat(), "mode_reglement": "mobile_money"})
    db.session.remove()
    assert Facture.query.one().statut == "payee"


def test_facture_d_une_autre_ecole_invisible(client, db, creer_utilisateur):
    from app.models.ecole import Ecole
    from app.models.gouvernance import Facture

    db.session.add(Ecole(id=2, nom="Autre", sigle="AU", prefixe_matricule="AU26"))
    db.session.add(Facture(ecole_id=2, numero="FAC-2026-0099", date_echeance=date.today(), periode_debut=date.today(),
                           periode_fin=date.today(), libelle="x", montant=1000))
    db.session.commit()
    creer_utilisateur("Fond", "f@t.td", "fondateur")
    creer_utilisateur("Compt", "c@t.td", "comptable")
    connecter(client, "f@t.td")
    assert client.get("/etablissement/facture/1/pdf").status_code == 404
    assert "FAC-2026-0099" not in _texte(client.get("/etablissement/abonnement"))
    client.post("/auth/deconnexion")
    connecter(client, "c@t.td")
    assert client.get("/etablissement/abonnement").status_code == 403
    assert client.get("/plateforme/factures").status_code == 403


def test_assistance_entre_ecole_et_plateforme(client, db, creer_utilisateur):
    from app.models.gouvernance import DemandeSupport

    creer_utilisateur("Dev", "dev@t.td", "developpeur")
    creer_utilisateur("Fond", "f@t.td", "fondateur")
    connecter(client, "f@t.td")
    r = client.post("/etablissement/assistance", data={"sujet": "Besoin d'espace", "categorie": "stockage",
                                                       "contenu": "Pouvez-vous augmenter notre quota ?"}, follow_redirects=True)
    assert "Demande envoyée" in _texte(r)
    demande = DemandeSupport.query.one()
    assert demande.non_lu_plateforme
    client.post("/auth/deconnexion")
    _oublier_utilisateur()

    connecter(client, "dev@t.td")
    assert "Besoin d" in _texte(client.get("/plateforme/assistance"))
    client.post(f"/plateforme/assistance/{demande.id}", data={"contenu": "C'est fait : 10 Go.", "statut": "resolue"})
    client.post("/auth/deconnexion")
    _oublier_utilisateur()

    connecter(client, "f@t.td")
    assert "Nouvelle réponse" in _texte(client.get("/etablissement/assistance"))
    assert "C&#39;est fait : 10 Go." in _texte(client.get(f"/etablissement/assistance/{demande.id}"))
    db.session.remove()
    d = DemandeSupport.query.one()
    assert d.statut == "resolue" and not d.non_lu_ecole and len(d.messages) == 2


def test_annonce_de_la_plateforme_sur_le_tableau_de_bord(client, db, creer_utilisateur):
    creer_utilisateur("Dev", "dev@t.td", "developpeur")
    creer_utilisateur("Fond", "f@t.td", "fondateur")
    creer_utilisateur("Prof", "p@t.td", "enseignant")
    connecter(client, "dev@t.td")
    client.post("/plateforme/annonces", data={"titre": "Maintenance samedi", "contenu": "Coupure de 8 h à 9 h.", "public": "direction"})
    client.post("/auth/deconnexion")
    _oublier_utilisateur()
    connecter(client, "f@t.td")
    assert "Maintenance samedi" in _texte(client.get("/"))
    client.post("/auth/deconnexion")
    _oublier_utilisateur()
    connecter(client, "p@t.td")
    assert "Maintenance samedi" not in _texte(client.get("/"))


def test_journal_et_sauvegarde_depuis_la_console(client, db, creer_utilisateur):
    import zipfile
    from app.models.ecole import Ecole

    db.session.add(Ecole(id=2, nom="Autre", sigle="AU", prefixe_matricule="AU26"))
    db.session.commit()
    creer_utilisateur("Dev", "dev@t.td", "developpeur")
    creer_utilisateur("Fond B", "b@t.td", "fondateur", ecole_id=2)
    connecter(client, "dev@t.td")
    r = client.get("/plateforme/2/sauvegarde")
    assert r.mimetype == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.data)) as archive:
        assert "donnees.json" in archive.namelist()
        assert b"b@t.td" in archive.read("donnees.json")
    page = _texte(client.get("/plateforme/journal?ecole_id=2"))
    assert "sauvegarde_exportee" in page
    page = _texte(client.get("/plateforme/"))
    assert "Abonnement et stockage" in page and "utilisés sur" in page


def test_pages_sensibles_jamais_gardees_sur_l_appareil(client, creer_utilisateur):
    creer_utilisateur("Compt", "c@t.td", "comptable")
    connecter(client, "c@t.td")
    assert client.get("/caisse/").headers["Cache-Control"] == "no-store"
    assert "no-store" not in client.get("/calendrier/").headers.get("Cache-Control", "")
