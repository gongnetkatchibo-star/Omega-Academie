from app.models.tenant import AppartientEcole
from datetime import datetime

from app.extensions import db
from app.services.temps import maintenant

# Publication interne à l'application uniquement — l'envoi réel par
# SMS/email nécessitera un service comme Twilio ou une passerelle SMS
# locale (§9 du cahier des charges).
DESTINATAIRES = ["tous", "parent", "enseignant", "eleve"]

# Un enseignant ne peut pas diffuser à toute l'école (portée limitée à ses
# interlocuteurs directs) — décision prise en corrigeant l'incohérence
# relevée en septembre 2026.
DESTINATAIRES_ENSEIGNANT = ["parent", "enseignant", "eleve"]

LIBELLES_DESTINATAIRE = {
    "tous": "Toute l'école", "parent": "Parents", "enseignant": "Enseignants", "eleve": "Élèves",
}


class Annonce(AppartientEcole, db.Model):
    __tablename__ = "annonces"

    id = db.Column(db.Integer, primary_key=True)
    titre = db.Column(db.String(150), nullable=False)
    contenu = db.Column(db.Text, nullable=False)
    destinataire = db.Column(db.String(20), nullable=False, default="tous")
    nom_fichier = db.Column(db.String(255))
    # Pièce jointe enregistrée en base (comme les fichiers de la
    # bibliothèque) : elle suit l'annonce dans les sauvegardes. Chargée
    # seulement au téléchargement, jamais pour afficher la liste.
    fichier = db.deferred(db.Column(db.LargeBinary))
    fichier_mime = db.Column(db.String(100))
    auteur_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    date_publication = db.Column(db.DateTime, default=maintenant)

    auteur = db.relationship("User")

    @property
    def libelle_destinataire(self):
        return LIBELLES_DESTINATAIRE.get(self.destinataire, self.destinataire)

    def __repr__(self):
        return f"<Annonce {self.titre}>"
