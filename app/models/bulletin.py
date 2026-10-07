from app.models.tenant import AppartientEcole
from app.extensions import db


class CoefficientMatiere(AppartientEcole, db.Model):
    """Poids d'une matière dans la moyenne générale d'une classe.
    Sans ligne ici, la matière compte pour 1."""
    __tablename__ = "coefficients_matieres"
    __table_args__ = (
        db.UniqueConstraint("classe_id", "matiere", name="uq_coefficient_classe_matiere"),
    )

    id = db.Column(db.Integer, primary_key=True)
    classe_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False, index=True)
    matiere = db.Column(db.String(80), nullable=False)
    coefficient = db.Column(db.Float, nullable=False, default=1)


class AppreciationBulletin(AppartientEcole, db.Model):
    """Appréciation du conseil de classe sur le bulletin d'un élève,
    pour un trimestre ("T1", "T2", "T3") ou pour l'année ("AN")."""
    __tablename__ = "appreciations_bulletins"
    __table_args__ = (
        db.UniqueConstraint("eleve_id", "periode", "annee_scolaire", name="uq_appreciation_eleve_periode"),
    )

    id = db.Column(db.Integer, primary_key=True)
    eleve_id = db.Column(db.Integer, db.ForeignKey("eleves.id"), nullable=False, index=True)
    periode = db.Column(db.String(4), nullable=False)
    annee_scolaire = db.Column(db.String(9), nullable=False)
    texte = db.Column(db.String(400), nullable=False)
