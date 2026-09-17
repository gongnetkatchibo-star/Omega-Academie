"""Fixtures partagées par tous les tests (pytest).

Base en mémoire, recréée à zéro pour chaque test — aucun test ne peut
donc être influencé par un autre, ni toucher la vraie base."""

import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture
def app():
    application = create_app("testing")
    with application.app_context():
        yield application


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def client(app):
    return app.test_client()


def connecter(client, email, mot_de_passe="p12345678"):
    """Connecte un compte déjà créé en base — CSRF désactivé en config
    de test, donc pas besoin de jeton ici."""
    return client.post("/auth/connexion", data={"email": email, "mot_de_passe": mot_de_passe}, follow_redirects=True)


@pytest.fixture
def creer_utilisateur(db):
    from app.models.user import User

    def _creer(nom_complet, email, role, statut="actif", mot_de_passe="p12345678"):
        u = User(nom_complet=nom_complet, email=email, role=role, statut=statut)
        u.set_mot_de_passe(mot_de_passe)
        db.session.add(u)
        db.session.commit()
        return u

    return _creer


@pytest.fixture
def creer_classe(db):
    from app.models.eleve import Eleve
    from app.models.classe import Classe

    def _creer(nom="CP1", niveau=1, annee=None, frais_inscription=0, frais_tranche1=0, frais_tranche2=0):
        annee = annee or Eleve.annee_scolaire_courante()
        c = Classe(
            nom=nom, niveau=niveau, annee_scolaire=annee,
            frais_inscription=frais_inscription, frais_tranche1=frais_tranche1, frais_tranche2=frais_tranche2,
        )
        db.session.add(c)
        db.session.commit()
        return c

    return _creer


@pytest.fixture
def creer_eleve(db):
    from app.models.eleve import Eleve

    def _creer(nom_complet, classe, sexe="M", matricule=None):
        e = Eleve(
            matricule=matricule or f"OA26-TEST-{nom_complet[:3].upper()}",
            nom_complet=nom_complet, classe_id=classe.id, sexe=sexe,
        )
        db.session.add(e)
        db.session.commit()
        return e

    return _creer
