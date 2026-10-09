"""Fixtures partagées par tous les tests (pytest).

Base en mémoire, recréée à zéro pour chaque test — aucun test ne peut
donc être influencé par un autre, ni toucher la vraie base."""

import os
import sqlite3

import pytest
from flask import has_request_context
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app import create_app
from app.extensions import db as _db

ECOLE_PAR_DEFAUT = 1


@event.listens_for(Engine, "connect")
def _cles_etrangeres_sqlite(connexion_dbapi, _):
    """Comme PostgreSQL en production : une ligne encore référencée ne
    peut pas être supprimée. SQLite ne le vérifie pas par défaut."""
    if isinstance(connexion_dbapi, sqlite3.Connection):
        curseur = connexion_dbapi.cursor()
        curseur.execute("PRAGMA foreign_keys=ON")
        curseur.close()


@event.listens_for(Session, "before_flush")
def _ecole_par_defaut_hors_requete(session_db, flush_context, instances):
    """Tests uniquement : les données créées directement par un test (hors
    requête HTTP) appartiennent à l'école n°1, sauf si le test précise
    une autre école. Les requêtes HTTP, elles, passent par le vrai
    mécanisme de l'application."""
    if has_request_context():
        return
    from app.services.tenant import modeles_rattaches, est_super_admin, ecole_courante_id

    ecole_par_defaut = ecole_courante_id() or ECOLE_PAR_DEFAUT

    types = tuple(modeles_rattaches())
    for objet in session_db.new:
        if isinstance(objet, types) and getattr(objet, "ecole_id", None) is None and not est_super_admin(objet):
            objet.ecole_id = ecole_par_defaut


# Par défaut, chaque test a sa propre base SQLite en mémoire. Pour lancer
# la suite sur PostgreSQL (la base de la production) :
#     TEST_DATABASE_URL=postgresql://utilisateur@127.0.0.1/base_d_essai pytest
# La base indiquée est VIDÉE avant chaque test : jamais la vraie base.
from config import avec_pilote

URL_POSTGRESQL = avec_pilote(os.environ.get("TEST_DATABASE_URL"))
if URL_POSTGRESQL and URL_POSTGRESQL == avec_pilote(os.environ.get("DATABASE_URL")):
    raise SystemExit("TEST_DATABASE_URL désigne la base de l'application : les tests l'effaceraient. Indique une base réservée aux tests.")


def _vider_base_postgresql():
    import sqlalchemy

    moteur = sqlalchemy.create_engine(URL_POSTGRESQL, isolation_level="AUTOCOMMIT")
    with moteur.connect() as connexion:
        connexion.execute(sqlalchemy.text("DROP SCHEMA public CASCADE"))
        connexion.execute(sqlalchemy.text("CREATE SCHEMA public"))
    moteur.dispose()


@pytest.fixture
def app():
    if URL_POSTGRESQL:
        _vider_base_postgresql()
    application = create_app("testing")
    with application.app_context():
        from app.models.ecole import Ecole
        _db.session.add(Ecole(id=ECOLE_PAR_DEFAUT, nom="École Test", sigle="ET", ville="Pala",
                              pays="Tchad", slogan="Devise test", prefixe_matricule="ET26"))
        _db.session.commit()
        if URL_POSTGRESQL:
            # Les tests créent des écoles avec un numéro imposé (1, 2, 3…) :
            # le compteur de PostgreSQL repart plus loin pour ne pas les heurter.
            from sqlalchemy import text
            _db.session.execute(text("SELECT setval('ecoles_id_seq', 1000)"))
            _db.session.commit()
        yield application
        if URL_POSTGRESQL:
            _db.session.remove()
            _db.engine.dispose()


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

    def _creer(nom_complet, email, role, statut="actif", mot_de_passe="p12345678", ecole_id=None):
        u = User(nom_complet=nom_complet, email=email, role=role, statut=statut, ecole_id=ecole_id)
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
