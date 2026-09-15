from datetime import datetime

from app.extensions import db

DECISIONS = ["en_attente", "admis", "refuse"]
LIBELLES_DECISION = {"en_attente": "En attente", "admis": "Admis", "refuse": "Refusé"}


class TestNiveau(db.Model):
    __tablename__ = "tests_niveau"

    id = db.Column(db.Integer, primary_key=True)
    nom_candidat = db.Column(db.String(120), nullable=False)
    date_naissance_candidat = db.Column(db.Date)
    classe_demandee_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    date_test = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    note_obtenue = db.Column(db.Float)
    decision = db.Column(db.String(20), nullable=False, default="en_attente")
    observation = db.Column(db.String(300))
    evaluateur_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    # Renseigné après coup si le candidat est effectivement inscrit comme
    # élève (le test précède souvent la création du dossier officiel).
    eleve_id = db.Column(db.Integer, db.ForeignKey("eleves.id"))
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    classe_demandee = db.relationship("Classe")
    evaluateur = db.relationship("User")
    eleve = db.relationship("Eleve")

    def __repr__(self):
        return f"<TestNiveau {self.nom_candidat} -> {self.classe_demandee_id}>"
