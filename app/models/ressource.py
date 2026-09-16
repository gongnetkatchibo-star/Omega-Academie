from datetime import datetime

from app.extensions import db

TYPES_RESSOURCE = ["livre", "cours", "exercice", "video"]


class Ressource(db.Model):
    __tablename__ = "ressources"

    id = db.Column(db.Integer, primary_key=True)
    titre = db.Column(db.String(150), nullable=False)
    type = db.Column(db.String(20), nullable=False, default="cours")
    matiere = db.Column(db.String(80))
    description = db.Column(db.Text)
    nom_fichier = db.Column(db.String(255), nullable=False)
    ajoute_par_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    date_ajout = db.Column(db.DateTime, default=datetime.utcnow)

    # Le bibliothécaire peut verrouiller une ressource sensible ou rare :
    # elle reste consultable en ligne (lecture inline) mais ne peut plus
    # être téléchargée ni sortir dans un export groupé (sept. 2026).
    consultation_sur_place = db.Column(db.Boolean, default=False, nullable=False)

    ajoute_par = db.relationship("User")

    def __repr__(self):
        return f"<Ressource {self.titre}>"
