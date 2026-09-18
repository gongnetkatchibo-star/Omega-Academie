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
