from datetime import datetime

from app.extensions import db
from app.models.tenant import AppartientEcole
from app.services.temps import maintenant

TYPES_EVALUATION = ["interrogation", "devoir", "composition"]
LIBELLES_TYPE = {"interrogation": "Interrogation", "devoir": "Devoir", "composition": "Composition"}


class Evaluation(AppartientEcole, db.Model):
    """Une évaluation notée d'une classe dans une matière : interrogation,
    devoir ou composition. La moyenne d'une matière est la moyenne de
    ses évaluations, pondérée par leur coefficient."""
    __tablename__ = "evaluations"

    id = db.Column(db.Integer, primary_key=True)
    classe_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False, index=True)
    matiere = db.Column(db.String(80), nullable=False)
    trimestre = db.Column(db.String(10), nullable=False)
    annee_scolaire = db.Column(db.String(9), nullable=False)
    titre = db.Column(db.String(120), nullable=False)
    type = db.Column(db.String(20), nullable=False, default="devoir")
    date = db.Column(db.Date, nullable=False)
    coefficient = db.Column(db.Float, nullable=False, default=1)
    enseignant_id = db.Column(db.Integer, db.ForeignKey("enseignants.id"))
    date_creation = db.Column(db.DateTime, default=maintenant)

    classe = db.relationship("Classe")
    notes = db.relationship("Note", back_populates="evaluation", cascade="all, delete-orphan")

    @property
    def libelle_type(self):
        return LIBELLES_TYPE.get(self.type, self.type)
