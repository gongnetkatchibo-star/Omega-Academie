from app.extensions import db
from app.models.tenant import AppartientEcole


class FraisAnnexe(AppartientEcole, db.Model):
    """Frais en plus de la scolarité (tenue, examen, transport…), pour
    une classe ou pour toute l'école, avec une date limite éventuelle."""
    __tablename__ = "frais_annexes"

    id = db.Column(db.Integer, primary_key=True)
    libelle = db.Column(db.String(80), nullable=False)
    montant = db.Column(db.Float, nullable=False)
    annee_scolaire = db.Column(db.String(9), nullable=False)
    classe_id = db.Column(db.Integer, db.ForeignKey("classes.id"), index=True)  # vide = toutes les classes
    date_limite = db.Column(db.Date)

    classe = db.relationship("Classe")
