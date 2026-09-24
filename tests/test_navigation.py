"""Navigation : tout passe par la barre latérale, le tableau de bord ne
montre que le logo, et aucun accès n'est perdu pour parents et élèves."""

from tests.conftest import connecter


def test_tableau_de_bord_sans_cartes(client, creer_utilisateur):
    creer_utilisateur("Fond", "fond@test.com", "fondateur")
    connecter(client, "fond@test.com")
    html = client.get("/").data.decode()
    assert "carte-module" not in html
    assert "logo-omega-academie.png" in html
    assert "Vers l'excellence et la sagesse" in html or "Vers l&#39;excellence et la sagesse" in html


def test_finances_en_liste_deroulante(client, creer_utilisateur):
    creer_utilisateur("Compt", "compt@test.com", "comptable")
    connecter(client, "compt@test.com")
    html = client.get("/").data.decode()
    assert 'class="sidebar-deroulant"' in html
    for lien in ["/finances/", "/caisse/", "/salaires/"]:
        assert f'href="{lien}"' in html


def test_parent_garde_acces_fiche_scolarite_bulletin(client, creer_utilisateur, creer_classe, creer_eleve):
    parent = creer_utilisateur("Parent", "parent@test.com", "parent")
    classe = creer_classe()
    eleve = creer_eleve("Awa Mbaye", classe)
    eleve.parents.append(parent)
    from app.extensions import db
    db.session.commit()

    connecter(client, "parent@test.com")
    html = client.get("/").data.decode()
    assert "Awa Mbaye" in html
    assert f'href="/eleves/{eleve.id}"' in html
    assert f'href="/finances/{eleve.id}"' in html
    assert f'/bulletin/{eleve.id}"' in html
