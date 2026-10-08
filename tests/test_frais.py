"""Frais : dates limites et retards, remise, frais annexes, montants entiers."""

from datetime import date, timedelta

import pytest

from tests.conftest import connecter


@pytest.fixture
def scolarite(client, db, creer_utilisateur, creer_classe, creer_eleve):
    creer_utilisateur("Fond", "f@t.com", "fondateur")
    classe = creer_classe(nom="CM1", niveau=5, frais_inscription=10000, frais_tranche1=30000, frais_tranche2=20000)
    eleve = creer_eleve("Awa", classe, matricule="ET26-CM1-001")
    connecter(client, "f@t.com")
    return {"eleve": eleve.id, "classe": classe.id}


def _resume(db, eleve_id):
    from flask import g
    from app.models.eleve import Eleve
    from app.services.paiements import resume_paiements

    g.pop("_contexte_frais", None)
    db.session.expire_all()
    return resume_paiements(db.session.get(Eleve, eleve_id))


def test_retard_apres_la_date_limite(client, db, scolarite):
    hier, demain = date.today() - timedelta(days=1), date.today() + timedelta(days=30)
    client.post("/developpeur/parametres", data={
        "nom": "École Test", "sigle": "ET", "prefixe_matricule": "ET26",
        "date_limite_inscription": hier.isoformat(), "date_limite_tranche_1": demain.isoformat(),
    })
    r = _resume(db, scolarite["eleve"])
    assert r["retard"] == 10000
    assert [e["en_retard"] for e in r["echeances"]] == [True, False, False]

    client.post(f"/finances/{scolarite['eleve']}", data={"montant": "4000", "mode": "especes", "echeance": "inscription"})
    assert _resume(db, scolarite["eleve"])["retard"] == 6000
    page = client.get("/finances/?retard=1").get_data(as_text=True)
    assert "Awa" in page and "6\u00a0000\u00a0FCFA" in page
    client.post(f"/finances/{scolarite['eleve']}", data={"montant": "6000", "mode": "especes", "echeance": "inscription"})
    assert _resume(db, scolarite["eleve"])["retard"] == 0
    assert "Aucun élève en retard" in client.get("/finances/?retard=1").get_data(as_text=True)


def test_remise_reduit_le_montant_du(client, db, scolarite):
    r = client.post(f"/finances/{scolarite['eleve']}/remise", data={"remise_pourcent": "25", "remise_motif": "Fratrie"},
                    follow_redirects=True)
    assert "Remise de 25 %" in r.get_data(as_text=True) and "Fratrie" in r.get_data(as_text=True)
    resume = _resume(db, scolarite["eleve"])
    assert [e["attendu"] for e in resume["echeances"]] == [7500, 22500, 15000] and resume["du"] == 45000
    assert "entre 0 et 100" in client.post(f"/finances/{scolarite['eleve']}/remise", data={"remise_pourcent": "150"},
                                           follow_redirects=True).get_data(as_text=True)


def test_remise_reservee_a_la_direction(client, db, scolarite, creer_utilisateur):
    from flask import g

    creer_utilisateur("Compta", "c@t.com", "comptable")
    client.get("/auth/deconnexion")
    g.pop("_login_user", None)
    connecter(client, "c@t.com")
    assert client.post(f"/finances/{scolarite['eleve']}/remise", data={"remise_pourcent": "100"}).status_code == 403
    assert "Enregistrer la remise" not in client.get(f"/finances/{scolarite['eleve']}").get_data(as_text=True)


def test_frais_annexe_par_classe_et_paiement(client, db, scolarite, creer_classe, creer_eleve):
    from app.models.frais_annexe import FraisAnnexe
    from app.models.mouvement_caisse import MouvementCaisse
    from app.models.paiement import Paiement

    autre_classe = creer_classe(nom="CM2", niveau=6)
    autre = creer_eleve("Ben", autre_classe, matricule="ET26-CM2-001")
    client.post("/finances/frais-annexes", data={"libelle": "Tenue", "montant": "5000", "classe_id": scolarite["classe"]})
    client.post("/finances/frais-annexes", data={"libelle": "Examen blanc", "montant": "2000", "classe_id": ""})
    tenue = FraisAnnexe.query.filter_by(libelle="Tenue").one()

    resume = _resume(db, scolarite["eleve"])
    assert [a["libelle"] for a in resume["annexes"]] == ["Tenue", "Examen blanc"] and resume["du"] == 67000
    assert [a["libelle"] for a in _resume(db, autre.id)["annexes"]] == ["Examen blanc"]

    r = client.post(f"/finances/{scolarite['eleve']}", data={"montant": "5000", "mode": "especes", "echeance": f"annexe_{tenue.id}"},
                    follow_redirects=True)
    assert "Paiement enregistré" in r.get_data(as_text=True)
    paiement = Paiement.query.one()
    assert paiement.echeance == "annexe" and paiement.libelle_echeance == "Tenue"
    assert MouvementCaisse.query.one().libelle.startswith("Tenue — Awa")
    resume = _resume(db, scolarite["eleve"])
    assert resume["annexes"][0]["reste"] == 0 and resume["paye"] == 5000
    assert [e["paye"] for e in resume["echeances"]] == [0, 0, 0]

    # Un frais d'une autre classe n'est pas payable par cet élève.
    r = client.post(f"/finances/{autre.id}", data={"montant": "5000", "mode": "especes", "echeance": f"annexe_{tenue.id}"},
                    follow_redirects=True)
    assert "montant valide" in r.get_data(as_text=True) and Paiement.query.count() == 1
    # Un frais déjà encaissé ne se supprime pas.
    r = client.post(f"/finances/frais-annexes/{tenue.id}/supprimer", follow_redirects=True)
    assert "Impossible de supprimer" in r.get_data(as_text=True)
    assert "Tenue" in client.get("/finances/frais-annexes").get_data(as_text=True)


@pytest.mark.parametrize("saisie", ["1500.50", "0", "-200", "abc", ""])
def test_montants_non_entiers_refuses(client, db, scolarite, saisie):
    from app.models.paiement import Paiement

    client.post(f"/finances/{scolarite['eleve']}", data={"montant": saisie, "mode": "especes", "echeance": "inscription"})
    assert Paiement.query.count() == 0
