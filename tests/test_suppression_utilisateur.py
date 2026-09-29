"""Suppression d'un compte : elle doit réussir même si la personne a un
historique (journal, téléphones, messages, fichiers, élève lié…),
sans effacer l'historique des autres."""

from tests.conftest import connecter


def test_supprimer_un_utilisateur_avec_historique(client, db, creer_utilisateur, creer_classe, creer_eleve):
    from app.models.user import User
    from app.models.journal import JournalAction
    from app.models.telephone import NumeroTelephone
    from app.models.message import Message
    from app.models.ressource import Ressource
    from app.models.enseignant import Enseignant

    creer_utilisateur("Dev", "dev@t.com", "developpeur")
    cible = creer_utilisateur("Jean D'Almeida", "jean@t.com", "parent")
    prof = creer_utilisateur("Prof Sortant", "prof@t.com", "enseignant")
    eleve = creer_eleve("Enfant", creer_classe())
    eleve.parents.append(cible)
    db.session.add_all([
        JournalAction(utilisateur_id=cible.id, action="connexion"),
        NumeroTelephone(user_id=cible.id, numero="+23566000000", operateur="airtel"),
        Message(parent_id=cible.id, auteur_id=cible.id, contenu="Bonjour"),
        Ressource(titre="Cours", type="cours", nom_fichier="c.pdf", ajoute_par_id=prof.id,
                  contenu=b"x", consultation_sur_place=False),
        Enseignant(user_id=prof.id),
        JournalAction(utilisateur_id=prof.id, action="connexion"),
    ])
    db.session.commit()
    cible_id, prof_id = cible.id, prof.id

    connecter(client, "dev@t.com")
    for uid in (cible_id, prof_id):
        db.session.remove()
        r = client.post(f"/developpeur/utilisateur/{uid}/supprimer", follow_redirects=True)
        assert r.status_code == 200
        assert "supprimé définitivement" in r.get_data(as_text=True)

    db.session.remove()
    assert db.session.get(User, cible_id) is None
    assert db.session.get(User, prof_id) is None
    assert NumeroTelephone.query.count() == 0
    assert Message.query.count() == 0
    assert Ressource.query.count() == 1  # le fichier reste dans la bibliothèque
    assert JournalAction.query.filter_by(action="connexion").count() == 2  # historique conservé


def test_bouton_supprimer_fonctionne_avec_une_apostrophe_dans_le_nom(client, db, creer_utilisateur):
    """Une apostrophe dans le nom cassait le JavaScript de confirmation :
    le bouton Supprimer ne faisait plus rien."""
    import html

    creer_utilisateur("Dev", "dev@t.com", "developpeur")
    creer_utilisateur("Jean D'Almeida", "jean@t.com", "parent")
    connecter(client, "dev@t.com")
    page = client.get("/developpeur/").get_data(as_text=True)
    scripts = [html.unescape(m.split('"', 1)[0]) for m in page.split('onsubmit="')[1:] if "Almeida" in m.split('"', 1)[0]]
    assert scripts, "bouton de suppression introuvable"
    for js in scripts:
        assert js.startswith('return confirm("') and "D\\u0027Almeida" in js
