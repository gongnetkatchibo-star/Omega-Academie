"""Relances WhatsApp : message prêt à envoyer, sans frais, chaque envoi
noté dans le journal."""

from datetime import date, timedelta
from urllib.parse import unquote

import pytest

from tests.conftest import connecter


@pytest.fixture
def eleve_absent(db, creer_classe, creer_eleve):
    from app.models.absence import Absence
    from app.services.temps import aujourd_hui

    classe = creer_classe(nom="CE2", niveau=4, frais_inscription=25000, frais_tranche1=60000)
    eleve = creer_eleve("Achta Oumar", classe, sexe="F", matricule="ET26-CE2-001")
    eleve.telephone_parent = "66 12 34 56"
    eleve.personne_urgence = "Tante Zara"
    eleve.telephone_urgence = "+235 99 88 77 66"
    db.session.add(Absence(eleve_id=eleve.id, classe_id=classe.id, date=aujourd_hui(), justifiee=False))
    db.session.commit()
    return eleve


def test_contacts_sans_doublon_et_numeros_invalides_ignores(app, db, creer_utilisateur, eleve_absent):
    from app.models.telephone import NumeroTelephone
    from app.services.whatsapp import contacts

    parent = creer_utilisateur("Oumar Mahamat", "p@t.com", "parent")
    parent.telephone = "+23566123456"  # même numéro que le dossier
    db.session.add(NumeroTelephone(user_id=parent.id, numero="+23590000001", operateur="moov", libelle="Bureau"))
    eleve_absent.parents.append(parent)
    eleve_absent.telephone_urgence = "22 51 00 00"  # fixe : pas de WhatsApp
    db.session.commit()

    assert [(c["nom"], c["numero"], c["libelle"]) for c in contacts(eleve_absent)] == [
        ("Oumar Mahamat", "+23566123456", None),
        ("Oumar Mahamat", "+23590000001", "Bureau"),
    ]


def test_le_secretariat_previent_une_absence(client, db, creer_utilisateur, eleve_absent):
    from app.models.journal import JournalAction
    from app.services.temps import aujourd_hui

    creer_utilisateur("Secr", "s@t.com", "secretaire")
    connecter(client, "s@t.com")
    page = client.get("/relances/").get_data(as_text=True)
    assert "Achta Oumar" in page and "À prévenir" in page
    assert "+235 66 12 34 56" in page and "Tante Zara" in page
    assert "Paiements en retard" not in page  # pas d'accès aux finances

    r = client.post("/relances/envoyer", data={
        "type": "absence", "eleve_id": eleve_absent.id, "numero": "+23566123456", "date": aujourd_hui().isoformat(),
    })
    assert r.status_code == 302 and r.headers["Location"].startswith("https://wa.me/23566123456?text=")
    texte = unquote(r.headers["Location"])
    assert "École Test" in texte and "Achta Oumar (CE2) a été absente le" in texte

    action = JournalAction.query.filter_by(action="whatsapp_absence").one()
    assert action.cible_id == eleve_absent.id and aujourd_hui().isoformat() in action.details
    page = client.get("/relances/").get_data(as_text=True)
    assert "Prévenu à" in page and "par Secr" in page and "À prévenir" not in page


def test_numero_hors_dossier_refuse(client, creer_utilisateur, eleve_absent):
    creer_utilisateur("Secr", "s@t.com", "secretaire")
    connecter(client, "s@t.com")
    r = client.post("/relances/envoyer", data={
        "type": "absence", "eleve_id": eleve_absent.id, "numero": "+23561111111", "date": date.today().isoformat(),
    })
    assert r.status_code == 400


def test_droits_par_type_d_envoi(client, creer_utilisateur, eleve_absent):
    creer_utilisateur("Prof", "e@t.com", "enseignant")
    connecter(client, "e@t.com")
    assert client.get("/relances/").status_code == 403
    client.get("/auth/deconnexion")

    creer_utilisateur("Secr", "s@t.com", "secretaire")
    connecter(client, "s@t.com")
    r = client.post("/relances/envoyer", data={"type": "relance", "eleve_id": eleve_absent.id, "numero": "+23566123456"})
    assert r.status_code == 403  # le secrétariat n'a pas accès aux finances


def test_le_comptable_relance_un_paiement_en_retard(client, db, creer_utilisateur, eleve_absent):
    creer_utilisateur("Fond", "f@t.com", "fondateur")
    connecter(client, "f@t.com")
    hier = date.today() - timedelta(days=1)
    client.post("/developpeur/parametres", data={
        "nom": "École Test", "sigle": "ET", "prefixe_matricule": "ET26", "date_limite_inscription": hier.isoformat(),
    })
    client.get("/auth/deconnexion")
    from flask import g
    g.pop("_contexte_frais", None)  # les tests partagent le même g d'une requête à l'autre

    creer_utilisateur("Compt", "c@t.com", "comptable")
    connecter(client, "c@t.com")
    page = client.get("/relances/").get_data(as_text=True)
    assert "Paiements en retard" in page and "Achta Oumar" in page
    assert "25 000 FCFA en retard" in page
    assert "Absences non justifiées" not in page  # pas d'accès aux absences

    r = client.post("/relances/envoyer", data={"type": "relance", "eleve_id": eleve_absent.id, "numero": "+23599887766"})
    texte = unquote(r.headers["Location"])
    assert "Il reste 85 000 FCFA à régler pour la scolarité de Achta Oumar" in texte
    assert "Dont 25 000 FCFA dont la date limite est dépassée." in texte
    assert "Relancé le" in client.get("/relances/").get_data(as_text=True)

    fiche = client.get(f"/finances/{eleve_absent.id}").get_data(as_text=True)
    assert "Relancer la famille" in fiche and "bouton-whatsapp" in fiche


def test_tableau_de_bord_signale_les_parents_a_prevenir(client, creer_utilisateur, eleve_absent):
    from app.services.temps import aujourd_hui

    creer_utilisateur("Dir", "d@t.com", "directeur_primaire")
    connecter(client, "d@t.com")
    page = client.get("/").get_data(as_text=True)
    assert "Parents à prévenir" in page and 'href="/relances/"' in page

    client.post("/relances/envoyer", data={
        "type": "absence", "eleve_id": eleve_absent.id, "numero": "+23566123456", "date": aujourd_hui().isoformat(),
    })
    assert "Parents à prévenir" not in client.get("/").get_data(as_text=True)


def test_fiche_eleve_propose_d_ecrire_a_la_famille(client, creer_utilisateur, eleve_absent):
    creer_utilisateur("Secr", "s@t.com", "secretaire")
    connecter(client, "s@t.com")
    page = client.get(f"/eleves/{eleve_absent.id}").get_data(as_text=True)
    assert "Écrire à la famille sur WhatsApp" in page and 'value="contact"' in page

    r = client.post("/relances/envoyer", data={"type": "contact", "eleve_id": eleve_absent.id, "numero": "+23566123456"})
    assert "au sujet de Achta Oumar (CE2)" in unquote(r.headers["Location"])
