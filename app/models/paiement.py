from datetime import datetime

from app.extensions import db

# Enregistrement manuel du paiement — pas d'appel réel à une API Mobile
# Money ici (nécessiterait des identifiants marchands Orange/MTN, voir §9
# du cahier des charges).
MODES_PAIEMENT = ["especes", "mobile_money", "virement_bancaire"]

# Échéancier officiel 2026-2027 (fiche du fondateur) : chaque paiement se
# rattache à l'une de ces 3 échéances.
ECHEANCES = ["inscription", "tranche_1", "tranche_2"]
LIBELLES_ECHEANCE = {
    "inscription": "Inscription",
    "tranche_1": "Tranche 1 (novembre)",
    "tranche_2": "Tranche 2 (février)",
}


class Paiement(db.Model):
    __tablename__ = "paiements"

    id = db.Column(db.Integer, primary_key=True)
    eleve_id = db.Column(db.Integer, db.ForeignKey("eleves.id"), nullable=False)
    montant = db.Column(db.Float, nullable=False)
    mode = db.Column(db.String(20), nullable=False, default="especes")
    echeance = db.Column(db.String(20), nullable=False, default="inscription")
    numero_recu = db.Column(db.String(40))
    reference = db.Column(db.String(80))
    annee_scolaire = db.Column(db.String(9), nullable=False)
    date_paiement = db.Column(db.DateTime, default=datetime.utcnow)
    enregistre_par_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    eleve = db.relationship("Eleve", back_populates="paiements")
    enregistre_par = db.relationship("User")

    @staticmethod
    def generer_numero_recu():
        """Référence unique et lisible, générée automatiquement — jamais
        saisie à la main (exigence de la direction, sept. 2026)."""
        annee = datetime.utcnow().year
        rang = Paiement.query.count() + 1
        return f"REC-{annee}-{rang:05d}"

    def __repr__(self):
        return f"<Paiement eleve={self.eleve_id} {self.montant} ({self.mode})>"
