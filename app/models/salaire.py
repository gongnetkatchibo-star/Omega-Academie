from datetime import datetime

from app.extensions import db

STATUTS_SALAIRE = ["impaye", "paye"]
LIBELLES_STATUT_SALAIRE = {"impaye": "Impayé", "paye": "Payé"}
MOIS_LIBELLES = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


class Salaire(db.Model):
    __tablename__ = "salaires"
    __table_args__ = (
        db.UniqueConstraint("personnel_id", "mois", "annee", name="uq_salaire_personnel_periode"),
    )

    id = db.Column(db.Integer, primary_key=True)
    personnel_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    mois = db.Column(db.Integer, nullable=False)
    annee = db.Column(db.Integer, nullable=False)
    montant = db.Column(db.Float, nullable=False)
    statut = db.Column(db.String(20), nullable=False, default="impaye")
    date_paiement = db.Column(db.Date)
    responsable_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    # Coordonnées de la personne payée au moment du salaire — utile
    # quand elles diffèrent de son compte (ex. email personnel pour
    # recevoir l'avis de paiement), et pour garder une trace même si le
    # compte change plus tard (sept. 2026).
    fonction = db.Column(db.String(80))
    email_contact = db.Column(db.String(150))
    telephone_contact = db.Column(db.String(30))

    personnel = db.relationship("User", foreign_keys=[personnel_id])
    responsable = db.relationship("User", foreign_keys=[responsable_id])

    @property
    def libelle_periode(self):
        return f"{MOIS_LIBELLES[self.mois - 1]} {self.annee}"

    def __repr__(self):
        return f"<Salaire {self.personnel_id} {self.libelle_periode}>"
