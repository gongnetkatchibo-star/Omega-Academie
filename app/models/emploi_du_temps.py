from app.extensions import db

JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]


class Creneau(db.Model):
    __tablename__ = "creneaux"

    id = db.Column(db.Integer, primary_key=True)
    classe_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    enseignant_id = db.Column(db.Integer, db.ForeignKey("enseignants.id"))
    matiere = db.Column(db.String(80), nullable=False)
    jour = db.Column(db.String(10), nullable=False)
    heure_debut = db.Column(db.String(5), nullable=False)
    heure_fin = db.Column(db.String(5), nullable=False)

    classe = db.relationship("Classe")
    enseignant = db.relationship("Enseignant")

    def __repr__(self):
        return f"<Creneau classe={self.classe_id} {self.jour} {self.heure_debut}>"
