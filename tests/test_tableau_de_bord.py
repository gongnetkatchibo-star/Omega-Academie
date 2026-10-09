"""Tableau de bord de la direction : chiffres réels, et chaque bloc
réservé aux rôles qui ont accès au module concerné."""

from datetime import date

from tests.conftest import connecter


def _page(client):
    return client.get("/").get_data(as_text=True)


def _ecole_avec_un_paiement(client, creer_utilisateur, creer_classe, creer_eleve):
    creer_utilisateur("Amina Mahamat", "f@t.com", "fondateur")
    classe = creer_classe(nom="CM1", niveau=5, frais_inscription=25000, frais_tranche1=60000, frais_tranche2=60000)
    eleve = creer_eleve("Fatimé Idriss", classe, sexe="F", matricule="ET26-CM1-001")
    creer_eleve("Hassan Djibrine", classe, sexe="M", matricule="ET26-CM1-002")
    connecter(client, "f@t.com")
    client.post(f"/finances/{eleve.id}", data={"montant": "25000", "mode": "mobile_money", "echeance": "inscription"})
    return eleve


def test_la_direction_voit_l_argent_les_effectifs_et_les_absences(client, creer_utilisateur, creer_classe, creer_eleve):
    _ecole_avec_un_paiement(client, creer_utilisateur, creer_classe, creer_eleve)
    page = _page(client)

    assert "Bonjour, Amina" in page
    assert "Encaissé en" in page and "25 000" in page
    # 25 000 payés sur 290 000 dus (2 élèves × 145 000) : 9 %.
    assert "Recouvrement de l'année" in page and "9 %" in page
    assert "265 000 FCFA" in page  # reste à recouvrer
    assert "Échéancier de la scolarité" in page and "50 000 FCFA" in page  # inscription attendue
    assert "Recouvrement par classe" in page and "badge-critique" in page
    assert "Derniers paiements" in page and "Fatimé Idriss" in page and "Mobile Money" in page
    assert "Élèves inscrits" in page and "1 filles · 1 garçons" in page
    assert "Absents aujourd'hui" in page and "Aucune absence n'a été signalée" in page


def test_le_secretariat_ne_voit_pas_les_montants(client, creer_utilisateur, creer_classe, creer_eleve):
    _ecole_avec_un_paiement(client, creer_utilisateur, creer_classe, creer_eleve)
    client.get("/auth/deconnexion")
    creer_utilisateur("Sec", "s@t.com", "secretaire")
    connecter(client, "s@t.com")
    page = _page(client)

    assert "Élèves inscrits" in page and "Absents aujourd'hui" in page
    assert "Échéancier de la scolarité" not in page
    assert "Derniers paiements" not in page
    assert "FCFA" not in page


def test_parent_et_enseignant_gardent_l_accueil_simple(client, creer_utilisateur):
    for role in ("parent", "enseignant"):
        creer_utilisateur(role, f"{role}@t.com", role)
        connecter(client, f"{role}@t.com")
        page = _page(client)
        assert "accueil-carte-ecole" in page, role
        assert "Élèves inscrits" not in page, role
        client.get("/auth/deconnexion")


def test_une_absence_du_jour_apparait_avec_sa_classe(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.absence import Absence
    from app.services.temps import aujourd_hui

    creer_utilisateur("Dir", "d@t.com", "directeur_primaire")
    classe = creer_classe(nom="CE2", niveau=4)
    eleve = creer_eleve("Achta Oumar", classe, sexe="F", matricule="ET26-CE2-001")
    db.session.add(Absence(eleve_id=eleve.id, classe_id=classe.id, date=aujourd_hui(), justifiee=False))
    db.session.commit()
    connecter(client, "d@t.com")
    page = _page(client)

    assert "Absences du jour" in page
    assert "CE2" in page and "1 absent" in page and "dont 1 non justifié" in page


def test_un_compte_en_attente_figure_dans_a_traiter(client, creer_utilisateur, creer_classe):
    creer_utilisateur("Fond", "f@t.com", "fondateur")
    creer_utilisateur("Nouveau parent", "n@t.com", "parent", statut="en_attente")
    creer_classe()
    connecter(client, "f@t.com")
    page = _page(client)
    assert "Comptes à valider" in page and 'href="/secretariat/demandes"' in page


def test_format_des_montants_et_des_dates(app):
    fcfa = app.jinja_env.filters["fcfa"]
    date_longue = app.jinja_env.filters["date_longue"]
    assert fcfa(145000) == "145 000 FCFA"
    assert fcfa(1234567.6, False) == "1 234 568"
    assert fcfa(None) == "0 FCFA"
    assert date_longue(date(2026, 10, 8)) == "jeudi 8 octobre 2026"
    assert date_longue(date(2026, 11, 1), False) == "1er novembre 2026"


def test_les_couleurs_disent_l_etat_des_chiffres(client, creer_utilisateur, creer_classe, creer_eleve):
    """Recouvrement à 9 % : tuile, jauge et badge passent au rouge. Une
    tranche dont la date limite n'est pas passée n'est pas jugée."""
    _ecole_avec_un_paiement(client, creer_utilisateur, creer_classe, creer_eleve)
    page = _page(client)

    assert 'class="tdb-indicateur tdb-ton-principal"' in page  # l'argent encaissé, seule tuile pleine
    assert 'class="tdb-indicateur tdb-ton-critique"' in page   # recouvrement de l'année
    assert 'class="tdb-indicateur tdb-ton-ok"' in page         # aucun absent
    assert '<tr class="tdb-ton-critique">' in page             # la classe CM1
    echeancier = page.split("Échéancier de la scolarité")[1].split("À traiter")[0]
    assert echeancier.count('class="badge') == 1  # seule l'inscription est due
