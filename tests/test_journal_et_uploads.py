"""Tests sur le journal d'actions et la validation des fichiers envoyés."""

import io

from tests.conftest import connecter


def test_changement_de_role_est_journalise(client, creer_utilisateur, db):
    from app.models.journal import JournalAction

    creer_utilisateur("Dev", "dev@test.com", "developpeur")
    secr = creer_utilisateur("Secr", "secr@test.com", "secretaire")

    connecter(client, "dev@test.com")
    client.post(f"/developpeur/utilisateur/{secr.id}", data={"role": "comptable", "statut": "actif"})

    entrees = JournalAction.query.all()
    assert len(entrees) == 1
    assert entrees[0].action == "modification_role_statut"
    assert "comptable" in entrees[0].details


def test_suppression_paiement_est_journalisee(client, creer_utilisateur, creer_classe, creer_eleve, db):
    from app.models.journal import JournalAction
    from app.models.paiement import Paiement

    creer_utilisateur("Fond", "fond@test.com", "fondateur")
    classe = creer_classe(frais_inscription=15000)
    eleve = creer_eleve("Eleve Test", classe)

    connecter(client, "fond@test.com")
    client.post(f"/finances/{eleve.id}", data={"echeance": "inscription", "montant": "15000", "mode": "especes"})
    paiement = Paiement.query.first()
    client.post(f"/finances/paiement/{paiement.id}/supprimer")

    entrees = JournalAction.query.filter_by(action="suppression_paiement").all()
    assert len(entrees) == 1


def test_upload_bibliotheque_refuse_extension_dangereuse(client, creer_utilisateur):
    creer_utilisateur("Biblio", "biblio@test.com", "bibliothecaire")
    connecter(client, "biblio@test.com")

    from app.models.ressource import Ressource

    r = client.post(
        "/bibliotheque/nouvelle",
        data={"titre": "Suspect", "type": "cours", "fichier": (io.BytesIO(b"contenu"), "virus.exe")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert Ressource.query.count() == 0
    assert "non autorisé".encode() in r.data or b"non autoris" in r.data


def test_upload_bibliotheque_accepte_pdf(client, creer_utilisateur):
    creer_utilisateur("Biblio", "biblio@test.com", "bibliothecaire")
    connecter(client, "biblio@test.com")

    from app.models.ressource import Ressource

    client.post(
        "/bibliotheque/nouvelle",
        data={"titre": "Cours valide", "type": "cours", "fichier": (io.BytesIO(b"contenu"), "cours.pdf")},
        content_type="multipart/form-data",
    )
    assert Ressource.query.count() == 1


def test_fichier_bibliotheque_telechargeable_et_supprimable(client, creer_utilisateur):
    """Régression : le fichier doit survivre en base (pas sur un disque
    éphémère), et le bouton Supprimer doit réellement fonctionner (jeton
    CSRF présent) — sept. 2026."""
    creer_utilisateur("Biblio", "biblio@test.com", "bibliothecaire")
    connecter(client, "biblio@test.com")

    from app.models.ressource import Ressource

    client.post(
        "/bibliotheque/nouvelle",
        data={"titre": "Cours", "type": "cours", "fichier": (io.BytesIO(b"contenu-du-fichier"), "cours.pdf")},
        content_type="multipart/form-data",
    )
    ressource = Ressource.query.first()

    r = client.get(f"/bibliotheque/{ressource.id}/telecharger")
    assert r.status_code == 200
    assert r.data == b"contenu-du-fichier"

    client.post(f"/bibliotheque/{ressource.id}/supprimer")
    assert Ressource.query.count() == 0


def test_piece_jointe_annonce_refuse_executable(client, creer_utilisateur):
    creer_utilisateur("Fond", "fond@test.com", "fondateur")
    connecter(client, "fond@test.com")

    from app.models.annonce import Annonce

    client.post(
        "/communication/nouvelle",
        data={"titre": "Test", "contenu": "Contenu", "destinataire": "tous", "fichier": (io.BytesIO(b"x"), "malware.exe")},
        content_type="multipart/form-data",
    )
    assert Annonce.query.count() == 0
