"""Bulletin : coefficients, rang, moyenne de classe, appréciation, PDF."""

import pytest
from flask import g

from tests.conftest import connecter


@pytest.fixture
def classe_notee(db, creer_classe, creer_eleve):
    from app.models.note import Note
    from app.models.bulletin import CoefficientMatiere

    classe = creer_classe(nom="6e", niveau=7)
    awa = creer_eleve("Awa", classe, matricule="ET26-6E-001")
    ben = creer_eleve("Ben", classe, matricule="ET26-6E-002")
    cle = creer_eleve("Clé", classe, matricule="ET26-6E-003")
    sans = creer_eleve("Sans Note", classe, matricule="ET26-6E-004")
    a = classe.annee_scolaire
    for eleve, maths, francais in [(awa, 16, 10), (ben, 10, 16), (cle, 8, 9)]:
        db.session.add_all([
            Note(eleve_id=eleve.id, classe_id=classe.id, matiere="Maths", valeur=maths, bareme=20, trimestre="T1", annee_scolaire=a),
            Note(eleve_id=eleve.id, classe_id=classe.id, matiere="Français", valeur=francais, bareme=20, trimestre="T1", annee_scolaire=a),
        ])
    db.session.add(Note(eleve_id=awa.id, classe_id=classe.id, matiere="Maths", valeur=12, bareme=20, trimestre="T2", annee_scolaire=a))
    db.session.add(CoefficientMatiere(classe_id=classe.id, matiere="Maths", coefficient=3))
    db.session.commit()
    return {"classe": classe.id, "awa": awa.id, "ben": ben.id, "cle": cle.id, "sans": sans.id}


def test_moyenne_ponderee_rang_et_statistiques(app, db, classe_notee):
    from app.models.classe import Classe
    from app.services.bulletins import bulletins_de_la_classe

    classe = db.session.get(Classe, classe_notee["classe"])
    calcul = bulletins_de_la_classe(classe, "T1", classe.annee_scolaire)
    awa, ben, cle = (calcul["bulletins"][classe_notee[k]] for k in ("awa", "ben", "cle"))

    assert awa["moyenne"] == 14.5      # (16×3 + 10×1) / 4
    assert ben["moyenne"] == 11.5      # (10×3 + 16×1) / 4
    assert cle["moyenne"] == 8.25
    assert (awa["rang"], ben["rang"], cle["rang"]) == (1, 2, 3)
    assert calcul["effectif_classe"] == 3 and classe_notee["sans"] not in calcul["bulletins"]
    assert calcul["moyenne_classe"] == 11.42 and calcul["plus_forte"] == 14.5 and calcul["plus_faible"] == 8.25
    maths = next(l for l in awa["lignes"] if l["matiere"] == "Maths")
    assert maths["coefficient"] == 3 and maths["points"] == 48 and maths["rang"] == 1
    assert maths["classe"] == 11.33 and (maths["min"], maths["max"]) == (8, 16)
    assert maths["mention"] == "Très bien" and awa["mention"] == "Bien" and cle["mention"] == "Insuffisant"


def test_bulletin_annuel_et_decision(app, db, classe_notee):
    from app.models.classe import Classe
    from app.services.bulletins import bulletins_de_la_classe

    classe = db.session.get(Classe, classe_notee["classe"])
    calcul = bulletins_de_la_classe(classe, "AN", classe.annee_scolaire)
    awa, cle = calcul["bulletins"][classe_notee["awa"]], calcul["bulletins"][classe_notee["cle"]]
    assert awa["trimestres"] == {"T1": 14.5, "T2": 12.0, "T3": None}
    assert awa["moyenne"] == 13.25 and awa["decision"] == "Admis en classe supérieure"
    assert cle["decision"] == "Redouble"


def test_ex_aequo_partagent_le_rang(app):
    from app.services.bulletins import _rangs

    assert _rangs({"a": 15, "b": 15, "c": 12}) == {"a": 1, "b": 1, "c": 3}


def test_primaire_reste_sur_dix(app, db, creer_classe, creer_eleve):
    from app.models.note import Note
    from app.services.bulletins import bulletins_de_la_classe

    classe = creer_classe(nom="CP1", niveau=1)
    e = creer_eleve("Petit", classe)
    db.session.add(Note(eleve_id=e.id, classe_id=classe.id, matiere="Lecture", valeur=7, bareme=10, trimestre="T1", annee_scolaire=classe.annee_scolaire))
    db.session.commit()
    calcul = bulletins_de_la_classe(classe, "T1", classe.annee_scolaire)
    assert calcul["bareme"] == 10 and calcul["bulletins"][e.id]["moyenne"] == 7 and calcul["bulletins"][e.id]["mention"] == "Bien"


def test_ecran_bulletin_appreciation_et_pdf(client, db, creer_utilisateur, classe_notee):
    creer_utilisateur("Dir", "d@t.com", "directeur_college")
    connecter(client, "d@t.com")
    awa = classe_notee["awa"]
    page = client.get(f"/notes/bulletin/{awa}").get_data(as_text=True)
    assert "14.50 / 20" in page and "1er / 3" in page and "Appréciation du conseil" in page

    r = client.post(f"/notes/bulletin/{awa}/appreciation", data={"trimestre": "T1", "appreciation": "Très bon trimestre."}, follow_redirects=True)
    assert "Très bon trimestre." in r.get_data(as_text=True)

    for url in (f"/notes/bulletin/{awa}/pdf?trimestre=T1", f"/notes/bulletin/{awa}/pdf?trimestre=AN",
                f"/notes/classe/{classe_notee['classe']}/bulletins/pdf?trimestre=T1"):
        r = client.get(url)
        assert r.status_code == 200 and r.headers["Content-Type"] == "application/pdf" and r.get_data()[:4] == b"%PDF", url

    page = client.get(f"/notes/classe/{classe_notee['classe']}/bulletins").get_data(as_text=True)
    assert "Sans Note" in page and "Aucune note" in page
    assert client.get("/notes/").status_code == 200


def test_coefficients_modifiables_par_la_direction_seulement(client, db, creer_utilisateur, classe_notee):
    from app.models.bulletin import CoefficientMatiere

    creer_utilisateur("Dir", "d@t.com", "directeur_college")
    creer_utilisateur("Sec", "s@t.com", "secretaire")
    cid = classe_notee["classe"]
    connecter(client, "s@t.com")
    assert client.get(f"/notes/classe/{cid}/coefficients").status_code == 403
    client.get("/auth/deconnexion")
    g.pop("_login_user", None)
    connecter(client, "d@t.com")
    page = client.get(f"/notes/classe/{cid}/coefficients").get_data(as_text=True)
    assert "Français" in page and "Maths" in page
    client.post(f"/notes/classe/{cid}/coefficients", data={"coefficient_0": "2", "coefficient_1": "4"})
    db.session.expire_all()
    assert {c.matiere: c.coefficient for c in CoefficientMatiere.query.all()} == {"Français": 2, "Maths": 4}


def test_parent_voit_le_bulletin_de_son_enfant_seulement(client, db, creer_utilisateur, classe_notee):
    from app.models.eleve import Eleve

    parent = creer_utilisateur("Parent", "p@t.com", "parent")
    awa = db.session.get(Eleve, classe_notee["awa"])
    awa.parents.append(parent)
    db.session.commit()
    connecter(client, "p@t.com")
    page = client.get(f"/notes/bulletin/{classe_notee['awa']}").get_data(as_text=True)
    assert "14.50 / 20" in page and "Enregistrer l'appréciation" not in page.replace("&#39;", "'")
    assert client.get(f"/notes/bulletin/{classe_notee['awa']}/pdf").status_code == 200
    assert client.get(f"/notes/bulletin/{classe_notee['ben']}").status_code == 403
    assert client.post(f"/notes/bulletin/{classe_notee['awa']}/appreciation", data={"appreciation": "x"}).status_code == 403
