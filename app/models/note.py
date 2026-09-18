from datetime import datetime

from app.extensions import db


class Note(db.Model):
    """Une note ponctuelle pour un élève, dans une matière et un trimestre (Module 6)."""

    __tablename__ = "notes"

    id = db.Column(db.Integer, primary_key=True)
    eleve_id = db.Column(db.Integer, db.ForeignKey("eleves.id"), nullable=False)
    classe_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    matiere = db.Column(db.String(80), nullable=False)
    valeur = db.Column(db.Float, nullable=False)
    bareme = db.Column(db.Float, default=20)
    trimestre = db.Column(db.String(10), nullable=False)  # T1, T2, T3
    annee_scolaire = db.Column(db.String(9), nullable=False)
    enseignant_id = db.Column(db.Integer, db.ForeignKey("enseignants.id"))
    date_saisie = db.Column(db.DateTime, default=datetime.utcnow)

    eleve = db.relationship("Eleve")
    classe = db.relationship("Classe")
    enseignant = db.relationship("Enseignant")

    @property
    def valeur_sur_20(self):
        return round(self.valeur * 20 / self.bareme, 2) if self.bareme else 0.0

    def __repr__(self):
        return f"<Note eleve={self.eleve_id} {self.matiere} {self.valeur}/{self.bareme}>"
