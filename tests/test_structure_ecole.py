"""Structure de l'école (oct. 2026) : découpage de l'année (trimestres,
semestres, séquences), maternelle et lycée, liste des matières. Le
comportement par défaut (trimestres, primaire et collège, matières libres)
ne change pas."""

import pytest

from tests.conftest import connecter


def _texte(r):
    return r.get_data(as_text=True)


def _systeme(db, systeme):
    from app.models.parametre import ParametreEtablissement
    from flask import g
    g.ecole_id = 1
    parametre = ParametreEtablissement.get()
    parametre.systeme_periodes = systeme
    db.session.commit()


@pytest.fixture
def notes_semestres(db, creer_classe, creer_eleve):
    from app.models.note import Note
    classe = creer_classe(nom="6e", niveau=7)
    awa = creer_eleve("Awa", classe, matricule="M1")
    a = classe.annee_scolaire
    db.session.add_all([
        Note(eleve_id=awa.id, classe_id=classe.id, matiere="Maths", valeur=12, bareme=20, trimestre="S1", annee_scolaire=a),
        Note(eleve_id=awa.id, classe_id=classe.id, matiere="Maths", valeur=16, bareme=20, trimestre="S2", annee_scolaire=a),
    ])
    db.session.commit()
    return classe, awa


# ------------------------------------------------------------ périodes
def test_par_defaut_toujours_des_trimestres(app):
    from app.services.periodes import periodes, periodes_et_annee
    with app.test_request_context():
        assert periodes() == ["T1", "T2", "T3"] and periodes_et_annee()[-1] == "AN"


def test_bulletin_et_moyenne_en_semestres(app, db, notes_semestres):
    from app.services.bulletins import bulletins_de_la_classe
    from app.services.moyennes import moyenne_eleve
    classe, awa = notes_semestres
    with app.test_request_context():
        _systeme(db, "semestres")
        s1 = bulletins_de_la_classe(classe, "S1", classe.annee_scolaire)
        assert s1["bulletins"][awa.id]["moyenne"] == 12 and s1["libelle_periode"] == "1er semestre"
        annee = bulletins_de_la_classe(classe, "AN", classe.annee_scolaire)
        assert annee["bulletins"][awa.id]["trimestres"] == {"S1": 12.0, "S2": 16.0}
        assert annee["bulletins"][awa.id]["moyenne"] == 14.0
        assert moyenne_eleve(awa, classe.annee_scolaire) == 14.0  # même calcul que le bulletin


def test_pages_de_notes_en_sequences(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.enseignant import Enseignant, Affectation
    from app.models.evaluation import Evaluation
    classe = creer_classe(nom="6e", niveau=7)
    creer_eleve("Awa", classe, matricule="M1")
    prof = creer_utilisateur("Prof", "p@t.td", "enseignant")
    profil = Enseignant(user_id=prof.id)
    db.session.add(profil)
    db.session.commit()
    db.session.add(Affectation(enseignant_id=profil.id, classe_id=classe.id, matiere="Maths"))
    db.session.commit()
    from app.models.parametre import ParametreEtablissement
    parametre = ParametreEtablissement.get()
    parametre.systeme_periodes = "sequences"
    db.session.commit()

    connecter(client, "p@t.td")
    page = _texte(client.get(f"/notes/classe/{classe.id}"))
    assert "6e séquence" in page and "1er trimestre" not in page
    client.post(f"/notes/classe/{classe.id}", data={"matiere": "Maths", "trimestre": "T1", "titre": "Devoir",
                                                     "type": "devoir", "coefficient": "1", "date": "2026-10-05"})
    assert Evaluation.query.count() == 0  # T1 n'existe pas en séquences
    client.post(f"/notes/classe/{classe.id}", data={"matiere": "Maths", "trimestre": "Q4", "titre": "Devoir",
                                                     "type": "devoir", "coefficient": "1", "date": "2026-10-05"})
    assert Evaluation.query.one().trimestre == "Q4"


def test_changement_de_decoupage_refuse_si_notes_deja_saisies(client, db, creer_utilisateur, notes_semestres):
    from app.models.parametre import ParametreEtablissement
    creer_utilisateur("Fondateur", "f@t.td", "fondateur")
    connecter(client, "f@t.td")
    # Les notes de l'année sont en S1/S2 : passer aux séquences est refusé…
    client.post("/classes/structure", data={"action": "periodes", "systeme_periodes": "sequences"})
    db.session.expire_all()
    assert ParametreEtablissement.get().systeme_periodes == "trimestres"
    # … le passage aux semestres, qui les contient, est accepté.
    client.post("/classes/structure", data={"action": "periodes", "systeme_periodes": "semestres"})
    db.session.expire_all()
    assert ParametreEtablissement.get().systeme_periodes == "semestres"


def test_seule_la_direction_regle_la_structure(client, creer_utilisateur):
    creer_utilisateur("Secrétaire", "s@t.td", "secretaire")
    connecter(client, "s@t.td")
    assert client.get("/classes/structure").status_code == 403


# ------------------------------------------------------- maternelle et lycée
def test_niveaux_maternelle_et_lycee_seulement_si_l_ecole_les_propose(client, db, creer_utilisateur):
    from app.models.classe import Classe
    from app.models.eleve import Eleve
    creer_utilisateur("Fondateur", "f@t.td", "fondateur")
    connecter(client, "f@t.td")
    assert "Petite section" not in _texte(client.get("/classes/nouvelle"))
    annee = Eleve.annee_scolaire_courante()
    client.post("/classes/nouvelle", data={"nom": "GS", "niveau": "0", "annee_scolaire": annee})
    assert Classe.query.count() == 0  # maternelle non proposée

    client.post("/classes/structure", data={"action": "cycles", "cycle_maternelle": "on", "cycle_lycee": "on"})
    page = _texte(client.get("/classes/nouvelle"))
    assert "Petite section" in page and "Terminale" in page
    client.post("/classes/nouvelle", data={"nom": "GS", "niveau": "0", "annee_scolaire": annee})
    client.post("/classes/nouvelle", data={"nom": "Tle D", "niveau": "13", "annee_scolaire": annee, "serie": "d"})
    gs, tle = Classe.query.filter_by(nom="GS").one(), Classe.query.filter_by(nom="Tle D").one()
    assert gs.niveau == 0 and gs.cycle == "Maternelle"
    assert tle.serie == "D" and tle.cycle == "Lycée"
    assert "série D" in _texte(client.get("/classes/"))


def test_baremes_et_directeurs_des_nouveaux_cycles(app, db, creer_classe):
    from app.services.moyennes import bareme_pour_classe
    from app.services.cycles import classe_dans_le_cycle
    from app.services.admission import bareme
    gs, tle = creer_classe(nom="GS", niveau=0), creer_classe(nom="Tle", niveau=13)
    assert bareme_pour_classe(gs) == 10 and bareme_pour_classe(tle) == 20
    assert bareme(gs) == (10, 5) and bareme(tle) == (20, 10)
    assert classe_dans_le_cycle(gs, "primaire") and classe_dans_le_cycle(tle, "college")


def test_nouvelle_annee_reprend_les_classes_a_serie(client, db, creer_utilisateur, creer_classe):
    from app.models.classe import Classe
    creer_utilisateur("Fondateur", "f@t.td", "fondateur")
    source = creer_classe(nom="1ère A4", niveau=12, annee="2025-2026", frais_inscription=40000)
    source.serie = "A4"
    db.session.commit()
    connecter(client, "f@t.td")
    client.post("/classes/demarrer-annee", data={"annee_scolaire": "2030-2031", "annee_source": "2025-2026"})
    copie = Classe.query.filter_by(nom="1ère A4", annee_scolaire="2030-2031").one()
    assert copie.serie == "A4" and copie.frais_inscription == 40000
    assert Classe.query.filter_by(annee_scolaire="2030-2031").count() == 11  # CP1→3ème + 1ère A4


# ------------------------------------------------------------------ matières
def test_matieres_libres_sans_liste_puis_imposees_avec_liste(client, db, creer_utilisateur, creer_classe):
    from app.models.enseignant import Enseignant, Affectation
    creer_utilisateur("Fondateur", "f@t.td", "fondateur")
    prof = creer_utilisateur("Prof", "p@t.td", "enseignant")
    profil = Enseignant(user_id=prof.id)
    db.session.add(profil)
    db.session.commit()
    classe = creer_classe(nom="6e", niveau=7)
    connecter(client, "f@t.td")

    client.post(f"/enseignants/{profil.id}/affecter", data={"classe_id": classe.id, "matiere": "Couture"})
    assert Affectation.query.count() == 1  # sans liste : saisie libre, comme avant

    client.post("/classes/structure", data={"action": "ajouter_matiere", "nom": "Maths\nFrançais\nmaths"})
    from app.models.matiere import matieres_officielles
    assert matieres_officielles() == ["Maths", "Français"]
    client.post(f"/enseignants/{profil.id}/affecter", data={"classe_id": classe.id, "matiere": "Poterie"})
    assert Affectation.query.count() == 1
    client.post(f"/enseignants/{profil.id}/affecter", data={"classe_id": classe.id, "matiere": "Maths"})
    assert Affectation.query.count() == 2
    assert '<select name="matiere"' in _texte(client.get(f"/enseignants/{profil.id}"))

    client.post("/classes/structure", data={"action": "reprendre_matieres"})
    assert "Couture" in matieres_officielles()
