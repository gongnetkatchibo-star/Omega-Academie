"""Une absence non justifiée prévient le parent le jour même."""

from tests.conftest import connecter


def test_parent_prevenu_d_une_absence_non_justifiee(client, db, monkeypatch, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.enseignant import Enseignant, Affectation

    envois = []
    monkeypatch.setattr("app.services.notifications.envoyer_email", lambda d, s, c, **k: envois.append((d, s, c)) or True)

    prof = creer_utilisateur("Prof", "e@t.com", "enseignant")
    parent = creer_utilisateur("Parent", "p@t.com", "parent")
    classe = creer_classe(nom="CM1", niveau=5)
    awa = creer_eleve("Awa", classe, matricule="ET26-CM1-001")
    ben = creer_eleve("Ben", classe, matricule="ET26-CM1-002")
    awa.parents.append(parent)
    ben.parents.append(parent)
    profil = Enseignant(user_id=prof.id)
    db.session.add(profil)
    db.session.flush()
    db.session.add(Affectation(enseignant_id=profil.id, classe_id=classe.id, matiere="Maths"))
    db.session.commit()
    classe_id, awa_id, ben_id = classe.id, awa.id, ben.id

    connecter(client, "e@t.com")
    client.post(f"/absences/classe/{classe_id}", data={
        "date": "2026-10-05", f"absent_{awa_id}": "on",
        f"absent_{ben_id}": "on", f"justifiee_{ben_id}": "on",
    })
    assert len(envois) == 1
    destinataires, sujet, corps = envois[0]
    assert destinataires == ["p@t.com"] and sujet == "Absence — Awa"
    assert "05/10/2026" in corps and "CM1" in corps

    # Réenregistrer le même appel ne renvoie pas d'email.
    client.post(f"/absences/classe/{classe_id}", data={"date": "2026-10-05", f"absent_{awa_id}": "on"})
    assert len(envois) == 1
    assert client.get("/absences/").status_code == 200
