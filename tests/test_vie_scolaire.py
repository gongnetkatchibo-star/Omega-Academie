"""Vie scolaire (oct. 2026) : cahier de textes et devoirs, retards et
discipline, calendrier scolaire, espace des familles, départ d'un élève."""

from datetime import timedelta

import pytest

from tests.conftest import connecter


def _texte(r):
    return r.get_data(as_text=True)


@pytest.fixture
def ecole(db, creer_utilisateur, creer_classe, creer_eleve):
    """Une classe de 6e avec un enseignant de maths, une autre classe,
    un élève dans chacune et un parent rattaché au premier."""
    from app.models.enseignant import Enseignant, Affectation

    prof = creer_utilisateur("Prof Maths", "prof@t.td", "enseignant")
    profil = Enseignant(user_id=prof.id)
    db.session.add(profil)
    db.session.commit()
    sixieme, cinquieme = creer_classe(nom="6e", niveau=7), creer_classe(nom="5e", niveau=8)
    db.session.add(Affectation(enseignant_id=profil.id, classe_id=sixieme.id, matiere="Maths"))
    awa = creer_eleve("Awa", sixieme, sexe="F", matricule="M1")
    ben = creer_eleve("Ben", cinquieme, matricule="M2")
    parent = creer_utilisateur("Parent Awa", "parent@t.td", "parent")
    awa.parents.append(parent)
    db.session.commit()
    return {"prof": prof, "profil": profil, "sixieme": sixieme, "cinquieme": cinquieme,
            "awa": awa, "ben": ben, "parent": parent}


def _aujourd_hui():
    from app.services.temps import aujourd_hui
    return aujourd_hui()


# ------------------------------------------------------------ cahier de textes
def test_enseignant_remplit_le_cahier_et_le_parent_voit_le_devoir(client, ecole):
    demain = (_aujourd_hui() + timedelta(days=1)).isoformat()
    connecter(client, "prof@t.td")
    r = client.post(f"/cahier-de-textes/classe/{ecole['sixieme'].id}", data={
        "matiere": "Maths", "date": _aujourd_hui().isoformat(), "contenu": "Fractions : addition",
        "devoir": "Exercices 3 et 4 page 12", "date_rendu": demain,
    }, follow_redirects=True)
    assert "Fractions : addition" in _texte(r)
    client.get("/auth/deconnexion")

    connecter(client, "parent@t.td")
    page = _texte(client.get(f"/cahier-de-textes/eleve/{ecole['awa'].id}"))
    assert "Exercices 3 et 4 page 12" in page
    # Le menu du parent mène aux devoirs, à l'emploi du temps et aux absences.
    accueil = _texte(client.get("/"))
    for lien in (f"/cahier-de-textes/eleve/{ecole['awa'].id}", f"/emploi-du-temps/eleve/{ecole['awa'].id}",
                 f"/absences/eleve/{ecole['awa'].id}"):
        assert lien in accueil, lien
    # Pas les devoirs d'un enfant qui n'est pas le sien.
    assert client.get(f"/cahier-de-textes/eleve/{ecole['ben'].id}").status_code == 403


def test_enseignant_n_ecrit_que_dans_ses_classes_et_ses_matieres(client, db, ecole):
    from app.models.cahier_textes import SeanceCahier

    connecter(client, "prof@t.td")
    assert client.get(f"/cahier-de-textes/classe/{ecole['cinquieme'].id}").status_code == 403
    client.post(f"/cahier-de-textes/classe/{ecole['sixieme'].id}", data={"matiere": "Anglais", "contenu": "x"})
    assert SeanceCahier.query.count() == 0


def test_direction_consulte_le_cahier_mais_parent_non(client, ecole, creer_utilisateur):
    creer_utilisateur("Directeur", "dir@t.td", "directeur_college")
    connecter(client, "dir@t.td")
    assert client.get(f"/cahier-de-textes/classe/{ecole['sixieme'].id}").status_code == 200
    client.get("/auth/deconnexion")
    connecter(client, "parent@t.td")
    assert client.get(f"/cahier-de-textes/classe/{ecole['sixieme'].id}").status_code == 403
    assert client.get("/cahier-de-textes/").status_code == 403


# ------------------------------------------------------------ discipline
def test_retard_et_sanction_au_registre_et_sur_la_page_de_l_eleve(client, ecole, monkeypatch):
    envois = []
    monkeypatch.setattr("app.services.notifications.envoyer_email", lambda d, s, c: envois.append(s) or True)
    connecter(client, "prof@t.td")
    awa = ecole["awa"]
    client.post("/discipline/nouveau", data={"eleve_id": awa.id, "type": "retard", "minutes": "15"})
    assert envois == []  # un premier retard ne déclenche pas d'email
    client.post("/discipline/nouveau", data={"eleve_id": awa.id, "type": "avertissement", "motif": "Bavardages"})
    assert envois == ["Avertissement — Awa"]
    registre = _texte(client.get("/discipline/"))
    assert "Bavardages" in registre and "15 min" in registre
    client.get("/auth/deconnexion")

    connecter(client, "parent@t.td")
    page = _texte(client.get(f"/absences/eleve/{awa.id}"))
    assert "Bavardages" in page and "Retards :" in page


def test_troisieme_retard_du_mois_previent_les_parents(client, ecole, monkeypatch):
    envois = []
    monkeypatch.setattr("app.services.notifications.envoyer_email", lambda d, s, c: envois.append(s) or True)
    connecter(client, "prof@t.td")
    for _ in range(3):
        client.post("/discipline/nouveau", data={"eleve_id": ecole["awa"].id, "type": "retard"})
    assert envois == ["Retards répétés — Awa"]


def test_enseignant_ne_signale_pas_un_eleve_d_une_autre_classe(client, ecole):
    from app.models.discipline import Incident

    connecter(client, "prof@t.td")
    client.post("/discipline/nouveau", data={"eleve_id": ecole["ben"].id, "type": "blame", "motif": "x"})
    assert Incident.query.count() == 0
    assert client.get("/discipline/nouveau").status_code == 200


def test_parent_n_accede_pas_au_registre(client, ecole):
    connecter(client, "parent@t.td")
    assert client.get("/discipline/").status_code == 403
    assert client.get("/discipline/nouveau").status_code == 403


# ------------------------------------------------------------ calendrier
def test_calendrier_tenu_par_le_secretariat_et_visible_par_les_familles(client, ecole, creer_utilisateur):
    creer_utilisateur("Secrétaire", "sec@t.td", "secretaire")
    debut = _aujourd_hui() + timedelta(days=5)
    connecter(client, "sec@t.td")
    client.post("/calendrier/nouveau", data={
        "titre": "Vacances de Noël", "type": "vacances", "date_debut": debut.isoformat(),
        "date_fin": (debut + timedelta(days=10)).isoformat(),
    })
    client.post("/calendrier/nouveau", data={
        "titre": "Conseil de classe", "type": "reunion", "date_debut": debut.isoformat(), "interne": "on",
    })
    client.post("/calendrier/nouveau", data={  # fin avant le début : refusé
        "titre": "Erreur", "type": "evenement", "date_debut": debut.isoformat(),
        "date_fin": (debut - timedelta(days=1)).isoformat(),
    })
    page = _texte(client.get("/calendrier/"))
    assert "Vacances de Noël" in page and "Conseil de classe" in page and "Erreur" not in page
    client.get("/auth/deconnexion")

    connecter(client, "parent@t.td")
    page = _texte(client.get("/calendrier/"))
    assert "Vacances de Noël" in page and "Conseil de classe" not in page
    assert "Vacances de Noël" in _texte(client.get("/"))  # « Prochainement » sur le tableau de bord
    assert client.post("/calendrier/nouveau", data={"titre": "X", "type": "ferie",
                                                    "date_debut": debut.isoformat()}).status_code == 403


# ------------------------------------------------------------ emploi du temps
def test_emploi_du_temps_pour_le_parent_et_pas_d_autre_classe_pour_l_eleve(client, db, ecole, creer_utilisateur):
    from app.models.emploi_du_temps import Creneau

    db.session.add(Creneau(classe_id=ecole["sixieme"].id, matiere="Maths", jour="Lundi",
                           heure_debut="08:00", heure_fin="09:00"))
    compte_awa = creer_utilisateur("Awa", "awa@t.td", "eleve")
    ecole["awa"].user_id = compte_awa.id
    db.session.commit()

    connecter(client, "parent@t.td")
    page = _texte(client.get(f"/emploi-du-temps/eleve/{ecole['awa'].id}"))
    assert "08:00" in page and "Ajouter un créneau" not in page
    assert client.get(f"/emploi-du-temps/eleve/{ecole['awa'].id}/pdf").mimetype == "application/pdf"
    assert client.get(f"/emploi-du-temps/eleve/{ecole['ben'].id}").status_code == 403
    client.get("/auth/deconnexion")

    connecter(client, "awa@t.td")
    assert client.get(f"/emploi-du-temps/classe/{ecole['sixieme'].id}").status_code == 200
    assert client.get(f"/emploi-du-temps/classe/{ecole['cinquieme'].id}").status_code == 403


# ------------------------------------------------------------ départ d'un élève
def test_radiation_certificat_puis_reintegration(client, db, ecole, creer_utilisateur):
    creer_utilisateur("Secrétaire", "sec@t.td", "secretaire")
    awa = ecole["awa"]
    connecter(client, "sec@t.td")
    client.post(f"/eleves/{awa.id}/radier", data={
        "motif_depart": "transfert", "date_depart": _aujourd_hui().isoformat(),
        "ecole_destination": "Lycée de Moundou",
    })
    db.session.expire_all()
    assert not awa.actif and awa.motif_depart == "transfert"
    assert "Awa" not in _texte(client.get("/eleves/"))
    anciens = _texte(client.get("/eleves/anciens"))
    assert "Awa" in anciens and "Lycée de Moundou" in anciens

    r = client.post(f"/documents/eleve/{awa.id}/radiation",
                    data={"signataire_nom": "M. X", "signataire_qualite": "Directeur", "signataire_genre": "M"})
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    # Plus de certificat de scolarité pour un élève parti.
    assert client.post(f"/documents/eleve/{awa.id}/certificat", data={}).status_code == 404

    client.post(f"/eleves/{awa.id}/reintegrer", data={"classe_id": ecole["sixieme"].id})
    db.session.expire_all()
    assert awa.actif and awa.motif_depart is None and awa.date_depart is None
    assert client.post(f"/documents/eleve/{awa.id}/radiation", data={}).status_code == 404


def test_seule_la_gestion_peut_radier(client, db, ecole):
    connecter(client, "prof@t.td")
    assert client.post(f"/eleves/{ecole['awa'].id}/radier", data={"motif_depart": "abandon"}).status_code == 403
    db.session.expire_all()
    assert ecole["awa"].actif


# ------------------------------------------------------------ traductions
def test_nouveaux_ecrans_traduits_en_arabe(app):
    from app.services.traductions_ar import INTERFACE

    for texte in ("Cahier de textes", "Retards et discipline", "Calendrier scolaire", "Devoirs",
                  "Absences et discipline", "Anciens élèves", "Départ de l'élève (radiation)",
                  "Signaler un retard ou un incident", "Prochainement", "Certificat de radiation (PDF)"):
        assert texte in INTERFACE, texte
