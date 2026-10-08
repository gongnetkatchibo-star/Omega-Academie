"""Tableau de bord : carte de l'école et cartes des guides d'utilisation."""

import pytest

from tests.conftest import connecter


def _page(client, url="/"):
    return client.get(url).get_data(as_text=True)


def test_tableau_de_bord_presente_la_plateforme_et_les_guides(client, creer_utilisateur):
    creer_utilisateur("Parent", "p@t.com", "parent")
    connecter(client, "p@t.com")
    page = _page(client)
    assert "accueil-carte-ecole" in page and "École Test" in page
    assert "Toute la gestion de l&#39;école au même endroit" in page
    assert "Guides d'utilisation" in page


def test_la_direction_garde_les_guides_sous_ses_chiffres(client, creer_utilisateur):
    creer_utilisateur("Fond", "f@t.com", "fondateur")
    connecter(client, "f@t.com")
    page = _page(client)
    assert "Bonjour, Fond" in page and "accueil-carte-ecole" not in page
    assert "Guides d'utilisation" in page
    for cle in ("classes", "eleves", "tests_niveau", "scolarite", "caisse", "salaires", "etablissement"):
        assert f'href="/guide/{cle}"' in page
    # Seulement l'aperçu sur le tableau de bord, pas le guide lui-même.
    assert "Primaire : sur 10" not in page


@pytest.mark.parametrize("role,visibles,caches", [
    ("parent", ["mes_enfants", "messagerie", "bibliotheque", "annonces", "profil"], ["classes", "caisse", "salaires", "roles", "plateforme"]),
    ("enseignant", ["classes", "eleves", "notes", "mon_edt"], ["caisse", "tests_niveau", "etablissement"]),
    ("comptable", ["scolarite", "caisse", "salaires", "statistiques"], ["tests_niveau", "enseignants", "mes_enfants"]),
    ("secretaire", ["classes", "eleves", "tests_niveau", "demandes", "alertes"], ["salaires", "plateforme"]),
    ("developpeur", ["plateforme", "roles", "etablissement", "caisse"], ["mon_espace", "mon_edt"]),
])
def test_chaque_espace_ne_voit_que_ses_guides(client, creer_utilisateur, role, visibles, caches):
    creer_utilisateur("Compte", "c@t.com", role)
    connecter(client, "c@t.com")
    page = _page(client)
    for cle in visibles:
        assert f'href="/guide/{cle}"' in page, cle
        assert client.get(f"/guide/{cle}").status_code == 200, cle
    for cle in caches:
        assert f'href="/guide/{cle}"' not in page, cle
        assert client.get(f"/guide/{cle}").status_code == 404, cle


def test_guide_ouvert_au_clic(client, creer_utilisateur):
    creer_utilisateur("Sec", "s@t.com", "secretaire")
    connecter(client, "s@t.com")
    page = _page(client, "/guide/tests_niveau")
    assert "Primaire : sur 10, admis à partir de 5" in page
    assert 'href="/tests-niveau/"' in page
    assert client.get("/guide/inconnu").status_code == 404


def test_guides_reserves_aux_comptes_connectes(client):
    assert client.get("/guide/classes").status_code in (302, 401)


def test_tous_les_guides_pointent_vers_un_ecran_existant(app):
    from flask import url_for
    from app.services.guides import GUIDES

    cles = [g["cle"] for g in GUIDES]
    assert len(cles) == len(set(cles))
    with app.test_request_context():
        for g in GUIDES:
            if g["endpoint"]:
                url_for(g["endpoint"])
            assert len(g["apercu"]) <= 90, g["cle"]
