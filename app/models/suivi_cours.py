from datetime import datetime

from app.extensions import db


class SuiviCours(db.Model):
    """Suivi de la progression d'un chapitre pour une classe/matière (Module 5)."""

    __tablename__ = "suivis_cours"

    id = db.Column(db.Integer, primary_key=True)
    classe_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    enseignant_id = db.Column(db.Integer, db.ForeignKey("enseignants.id"), nullable=False)
    matiere = db.Column(db.String(80), nullable=False)
    chapitre = db.Column(db.String(150), nullable=False)
    pourcentage = db.Column(db.Integer, default=0)  # 0-100
    en_retard = db.Column(db.Boolean, default=False)
    difficultes = db.Column(db.Text)
    date_maj = db.Column(db.DateTime, default=datetime.utcnow)

    classe = db.relationship("Classe")
    enseignant = db.relationship("Enseignant")

    def __repr__(self):
        return f"<SuiviCours {self.classe_id} {self.matiere} {self.chapitre} {self.pourcentage}%>"
