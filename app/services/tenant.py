"""Isolement des données entre établissements (mode SaaS).

Principe : l'école courante est fixée une fois par requête (g.ecole_id),
à partir du compte connecté. Deux écouteurs SQLAlchemy l'appliquent
ensuite partout, sans dépendre de chaque route :

- lecture : toute requête ORM sur un modèle rattaché à une école reçoit
  automatiquement « ecole_id = école courante » (y compris les
  chargements indirects comme eleve.classe ou get_or_404) ;
- écriture : toute nouvelle ligne sans ecole_id reçoit l'école courante.

Hors requête d'un utilisateur connecté (connexion, inscription, mot de
passe oublié), g.ecole_id vaut None et aucun filtre n'est appliqué — ces
écrans ne listent jamais de données d'école.

Une requête peut contourner le filtre de façon explicite avec
.execution_options(tous_etablissements=True) — réservé au chargement du
compte connecté et à la console plateforme."""

from flask import g, has_app_context, session
from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria
from sqlalchemy.orm.util import LoaderCriteriaOption

from app.extensions import db


def modeles_rattaches():
    from app.models.tenant import AppartientEcole

    return [m.class_ for m in db.Model.registry.mappers if issubclass(m.class_, AppartientEcole)]


def ecole_courante_id():
    if not has_app_context():
        return None
    return g.get("ecole_id")


def ecole_courante():
    from app.models.ecole import Ecole

    ecole_id = ecole_courante_id()
    if ecole_id is None:
        return None
    if "ecole_obj" not in g or g.ecole_obj is None or g.ecole_obj.id != ecole_id:
        g.ecole_obj = db.session.get(Ecole, ecole_id)
    return g.ecole_obj


def nom_ecole_courante():
    from flask import current_app

    ecole = ecole_courante()
    return ecole.nom if ecole else current_app.config.get("PLATEFORME_NOM", "Toumaï Edu School")


def est_super_admin(utilisateur):
    return utilisateur is not None and getattr(utilisateur, "role", None) == "developpeur"


def determiner_ecole(utilisateur):
    """École dans laquelle travaille ce compte pour la requête en cours.
    Un super-administrateur travaille dans l'école qu'il a choisie depuis
    la console (ou la première école s'il n'en a choisi aucune)."""
    from app.models.ecole import Ecole

    if utilisateur is None or not utilisateur.is_authenticated:
        return None
    if not est_super_admin(utilisateur):
        return utilisateur.ecole_id
    choisie = session.get("ecole_active")
    if choisie and db.session.get(Ecole, choisie) is not None:
        return choisie
    premiere = db.session.query(Ecole.id).order_by(Ecole.id).first()
    return premiere[0] if premiere else None


def installer_isolement(app):
    from app.models.tenant import AppartientEcole

    @event.listens_for(Session, "do_orm_execute")
    def _filtrer(execute_state):
        if execute_state.execution_options.get("tous_etablissements"):
            return
        if not (execute_state.is_select or execute_state.is_update or execute_state.is_delete):
            return
        ecole_id = ecole_courante_id()
        if ecole_id is None:
            return
        # Un objet chargé avec ce filtre le transmet aux objets liés qu'on
        # charge ensuite à partir de lui (élève → classe → élèves…). Le
        # rajouter à chaque étape l'empilait sans fin, jusqu'à dépasser la
        # limite de la base (constaté oct. 2026) : on ne l'ajoute que s'il
        # n'y est pas déjà.
        if any(
            isinstance(option, LoaderCriteriaOption) and option.root_entity is AppartientEcole
            for option in getattr(execute_state.statement, "_with_options", ())
        ):
            return
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                AppartientEcole, lambda cls: cls.ecole_id == ecole_id, include_aliases=True,
            )
        )

    @event.listens_for(Session, "before_flush")
    def _tamponner(session_db, flush_context, instances):
        ecole_id = ecole_courante_id()
        if ecole_id is None:
            return
        for objet in session_db.new:
            if isinstance(objet, AppartientEcole) and getattr(objet, "ecole_id", None) is None:
                if est_super_admin(objet):
                    continue
                objet.ecole_id = ecole_id
