from app.extensions import db


class HistoriqueScolaire(db.Model):
    __tablename__ = "historique_scolaire"

    id = db.Column(db.Integer, primary_key=True)
    eleve_id = db.Column(db.Integer, db.ForeignKey("eleves.id"), nullable=False)
    classe_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    annee_scolaire = db.Column(db.String(9), nullable=False)
    resultat = db.Column(db.String(20), default="en_cours")  # en_cours / admis / redouble

    eleve = db.relationship("Eleve", back_populates="historique")
    classe = db.relationship("Classe")

    def __repr__(self):
        return f"<Historique {self.eleve_id} {self.annee_scolaire}>"
