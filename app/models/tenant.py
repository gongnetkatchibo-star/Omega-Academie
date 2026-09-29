from sqlalchemy.orm import declared_attr

from app.extensions import db


class AppartientEcole:
    """À hériter par tout modèle dont les lignes appartiennent à un
    établissement. Le filtre (services/tenant.py) ajoute automatiquement
    « ecole_id = école courante » à chaque requête sur ces modèles, et
    remplit ecole_id sur toute nouvelle ligne."""

    @declared_attr
    def ecole_id(cls):
        return db.Column(db.Integer, db.ForeignKey("ecoles.id"), index=True)
