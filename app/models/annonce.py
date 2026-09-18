from datetime import datetime

from app.extensions import db

# Publication interne à l'application uniquement — l'envoi réel par
# SMS/email nécessitera un service comme Twilio ou une passerelle SMS
# locale (§9 du cahier des charges).
DESTINATAIRES = ["tous", "parent", "enseignant", "eleve"]

# Un enseignant ne peut pas diffuser à toute l'école (portée limitée à ses
# interlocuteurs directs) — décision prise en corrigeant l'incohérence
# relevée en septembre 2026.
DESTINATAIRES_ENSEIGNANT = ["parent", "enseignant", "eleve"]


class Annonce(db.Model):
    __tablename__ = "annonces"

    id = db.Column(db.Integer, primary_key=True)
    titre = db.Column(db.String(150), nullable=False)
    contenu = db.Column(db.Text, nullable=False)
    destinataire = db.Column(db.String(20), nullable=False, default="tous")
    nom_fichier = db.Column(db.String(255))
    auteur_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    date_publication = db.Column(db.DateTime, default=datetime.utcnow)

    auteur = db.relationship("User")

    def __repr__(self):
        return f"<Annonce {self.titre}>"
