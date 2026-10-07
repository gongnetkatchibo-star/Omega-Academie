from app.models.tenant import AppartientEcole
from datetime import datetime

from app.extensions import db
from app.services.temps import maintenant

# Enregistrement manuel du paiement — pas d'appel réel à une API Mobile
# Money ici (nécessiterait des identifiants marchands Orange/MTN, voir §9
# du cahier des charges).
MODES_PAIEMENT = ["especes", "mobile_money", "virement_bancaire"]

# Échéancier officiel 2026-2027 (fiche du fondateur) : chaque paiement se
# rattache à l'une de ces 3 échéances.
ECHEANCES = ["inscription", "tranche_1", "tranche_2"]
ECHEANCE_ANNEXE = "annexe"
LIBELLES_ECHEANCE = {
    "inscription": "Inscription",
    "tranche_1": "Tranche 1 (novembre)",
    "tranche_2": "Tranche 2 (février)",
}


class Paiement(AppartientEcole, db.Model):
    __tablename__ = "paiements"

    id = db.Column(db.Integer, primary_key=True)
    eleve_id = db.Column(db.Integer, db.ForeignKey("eleves.id"), nullable=False)
    montant = db.Column(db.Float, nullable=False)
    mode = db.Column(db.String(20), nullable=False, default="especes")
    echeance = db.Column(db.String(20), nullable=False, default="inscription")
    numero_recu = db.Column(db.String(40))
    reference = db.Column(db.String(80))
    annee_scolaire = db.Column(db.String(9), nullable=False)
    date_paiement = db.Column(db.DateTime, default=maintenant)
    enregistre_par_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    # Renseigné quand le paiement règle un frais annexe (echeance = "annexe").
    frais_annexe_id = db.Column(db.Integer, db.ForeignKey("frais_annexes.id"), index=True)

    eleve = db.relationship("Eleve", back_populates="paiements")
    enregistre_par = db.relationship("User")
    frais_annexe = db.relationship("FraisAnnexe")

    @property
    def libelle_echeance(self):
        if self.echeance == ECHEANCE_ANNEXE:
            return self.frais_annexe.libelle if self.frais_annexe else "Frais annexe"
        return LIBELLES_ECHEANCE.get(self.echeance, self.echeance)

    @staticmethod
    def generer_numero_recu():
        """Référence unique et lisible, générée automatiquement — jamais
        saisie à la main (exigence de la direction, sept. 2026)."""
        annee = maintenant().year
        rang = Paiement.query.count() + 1
        return f"REC-{annee}-{rang:05d}"

    def __repr__(self):
        return f"<Paiement eleve={self.eleve_id} {self.montant} ({self.mode})>"
