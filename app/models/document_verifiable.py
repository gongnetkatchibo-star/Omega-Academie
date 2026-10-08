import json

from app.models.tenant import AppartientEcole
from app.extensions import db
from app.services.temps import maintenant

TYPES_DOCUMENT = {
    "bulletin": "Bulletin de notes",
    "certificat": "Certificat de scolarité",
    "attestation": "Attestation de fréquentation",
    "radiation": "Certificat de radiation",
    "recu": "Reçu de paiement",
}


class DocumentVerifiable(AppartientEcole, db.Model):
    """Trace d'un document officiel émis par l'école, retrouvable par le
    code imprimé sous son QR code (oct. 2026).

    Les informations sont copiées au moment de l'émission et ne sont plus
    jamais recalculées : la page de vérification montre exactement ce que
    l'école a délivré. Une note ou un montant modifié sur le papier se
    voit donc tout de suite."""
    __tablename__ = "documents_verifiables"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    type_document = db.Column(db.String(20), nullable=False)
    # Ce que le document concerne, ex. "bulletin:12:T1" ou "recu:45" : sert
    # à redonner le même code quand le même document est réimprimé tel quel.
    cle_objet = db.Column(db.String(60), nullable=False, index=True)
    titre = db.Column(db.String(150), nullable=False)
    nom_eleve = db.Column(db.String(120))
    classe = db.Column(db.String(40))
    reference = db.Column(db.String(40))
    # Lignes « libellé : valeur » propres au document (moyenne, montant…),
    # en texte JSON : la sauvegarde par école sait le restaurer tel quel.
    details_json = db.Column(db.Text, nullable=False, default="[]")
    date_emission = db.Column(db.DateTime, nullable=False, default=maintenant)
    emis_par_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    annule = db.Column(db.Boolean, nullable=False, default=False)

    emis_par = db.relationship("User")

    @property
    def details(self):
        return [tuple(ligne) for ligne in json.loads(self.details_json or "[]")]

    @details.setter
    def details(self, lignes):
        self.details_json = json.dumps([list(ligne) for ligne in lignes], ensure_ascii=False)

    @property
    def libelle_type(self):
        return TYPES_DOCUMENT.get(self.type_document, self.type_document)

    def __repr__(self):
        return f"<DocumentVerifiable {self.code} {self.type_document}>"
