from app.models.tenant import AppartientEcole
from app.extensions import db
from app.services.temps import maintenant


class SeanceCahier(AppartientEcole, db.Model):
    """Une ligne du cahier de textes d'une classe : ce qui a été fait en
    cours et, s'il y en a, le travail à faire pour une date donnée."""

    __tablename__ = "seances_cahier"

    id = db.Column(db.Integer, primary_key=True)
    classe_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False, index=True)
    enseignant_id = db.Column(db.Integer, db.ForeignKey("enseignants.id"))
    matiere = db.Column(db.String(80), nullable=False)
    date = db.Column(db.Date, nullable=False)
    contenu = db.Column(db.Text, nullable=False)
    devoir = db.Column(db.Text)
    date_rendu = db.Column(db.Date)
    date_creation = db.Column(db.DateTime, default=maintenant)

    classe = db.relationship("Classe")
    enseignant = db.relationship("Enseignant")

    def __repr__(self):
        return f"<SeanceCahier {self.classe_id} {self.matiere} {self.date}>"
