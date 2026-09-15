from datetime import datetime

from app.extensions import db


class Absence(db.Model):
    __tablename__ = "absences"
    __table_args__ = (
        db.UniqueConstraint("eleve_id", "date", name="uq_absence_eleve_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    eleve_id = db.Column(db.Integer, db.ForeignKey("eleves.id"), nullable=False)
    classe_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    justifiee = db.Column(db.Boolean, default=False, nullable=False)
    motif = db.Column(db.String(200))
    enseignant_id = db.Column(db.Integer, db.ForeignKey("enseignants.id"))
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    eleve = db.relationship("Eleve")
    classe = db.relationship("Classe")
    enseignant = db.relationship("Enseignant")

    def __repr__(self):
        return f"<Absence eleve={self.eleve_id} {self.date}>"
