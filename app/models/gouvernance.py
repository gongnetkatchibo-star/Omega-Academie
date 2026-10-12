"""Gouvernance de la plateforme (oct. 2026) : abonnements et factures
des écoles, demandes d'assistance entre une école et l'administration de
la plateforme, annonces de la plateforme.

Ces tables appartiennent à la plateforme, pas aux écoles : elles ne
passent pas par le filtre automatique par école (pas d'AppartientEcole)
et ne font pas partie des sauvegardes d'une école. Chaque lecture côté
école filtre donc explicitement sur son ecole_id."""

from app.extensions import db
from app.services.temps import maintenant

MODES_FACTURATION = {
    "par_eleve": "Prix par élève et par période",
    "forfait": "Forfait par période",
}
PERIODICITES = {"mensuel": ("Mensuel", 1), "trimestriel": ("Trimestriel", 3), "annuel": ("Annuel", 12)}
STATUTS_FACTURE = {"emise": "À payer", "payee": "Payée", "annulee": "Annulée"}
MODES_REGLEMENT = {"mobile_money": "Mobile Money", "virement": "Virement", "especes": "Espèces", "autre": "Autre"}
STATUTS_DEMANDE = {"ouverte": "Ouverte", "en_cours": "En cours", "resolue": "Résolue"}
CATEGORIES_DEMANDE = {
    "question": "Question", "probleme": "Problème technique", "facturation": "Facturation",
    "stockage": "Espace de stockage", "suggestion": "Suggestion",
}
# Retard toléré après l'échéance avant que la plateforme ne signale l'école
# comme « à suspendre » (la suspension reste une décision manuelle).
JOURS_DE_GRACE = 15


class Facture(db.Model):
    __tablename__ = "factures_plateforme"

    id = db.Column(db.Integer, primary_key=True)
    ecole_id = db.Column(db.Integer, db.ForeignKey("ecoles.id"), nullable=False, index=True)
    numero = db.Column(db.String(30), unique=True, nullable=False)
    date_emission = db.Column(db.Date, nullable=False, default=lambda: maintenant().date())
    date_echeance = db.Column(db.Date, nullable=False)
    periode_debut = db.Column(db.Date, nullable=False)
    periode_fin = db.Column(db.Date, nullable=False)
    libelle = db.Column(db.String(200), nullable=False)
    quantite = db.Column(db.Integer, nullable=False, default=1)
    prix_unitaire = db.Column(db.Integer, nullable=False, default=0)
    montant = db.Column(db.Integer, nullable=False, default=0)
    statut = db.Column(db.String(10), nullable=False, default="emise")
    date_paiement = db.Column(db.Date)
    mode_reglement = db.Column(db.String(20))
    reference_reglement = db.Column(db.String(80))
    note = db.Column(db.String(300))

    ecole = db.relationship("Ecole")

    @property
    def libelle_statut(self):
        return STATUTS_FACTURE.get(self.statut, self.statut)

    @property
    def jours_de_retard(self):
        if self.statut != "emise":
            return 0
        return max(0, (maintenant().date() - self.date_echeance).days)


class DemandeSupport(db.Model):
    __tablename__ = "demandes_support"

    id = db.Column(db.Integer, primary_key=True)
    ecole_id = db.Column(db.Integer, db.ForeignKey("ecoles.id"), nullable=False, index=True)
    auteur_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    sujet = db.Column(db.String(150), nullable=False)
    categorie = db.Column(db.String(20), nullable=False, default="question")
    statut = db.Column(db.String(10), nullable=False, default="ouverte")
    date_creation = db.Column(db.DateTime, nullable=False, default=maintenant)
    date_maj = db.Column(db.DateTime, nullable=False, default=maintenant)
    # Non lu par l'autre partie depuis le dernier message.
    non_lu_plateforme = db.Column(db.Boolean, nullable=False, default=True)
    non_lu_ecole = db.Column(db.Boolean, nullable=False, default=False)

    ecole = db.relationship("Ecole")
    auteur = db.relationship("User")
    messages = db.relationship("MessageSupport", back_populates="demande", order_by="MessageSupport.id",
                               cascade="all, delete-orphan")

    @property
    def libelle_statut(self):
        return STATUTS_DEMANDE.get(self.statut, self.statut)

    @property
    def libelle_categorie(self):
        return CATEGORIES_DEMANDE.get(self.categorie, self.categorie)


class MessageSupport(db.Model):
    __tablename__ = "messages_support"

    id = db.Column(db.Integer, primary_key=True)
    demande_id = db.Column(db.Integer, db.ForeignKey("demandes_support.id"), nullable=False, index=True)
    auteur_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    de_la_plateforme = db.Column(db.Boolean, nullable=False, default=False)
    contenu = db.Column(db.Text, nullable=False)
    date_envoi = db.Column(db.DateTime, nullable=False, default=maintenant)

    demande = db.relationship("DemandeSupport", back_populates="messages")
    auteur = db.relationship("User")


class AnnoncePlateforme(db.Model):
    """Information de l'administration de la plateforme : maintenance,
    nouveauté… pour une école ou toutes, affichée sur le tableau de bord."""
    __tablename__ = "annonces_plateforme"

    id = db.Column(db.Integer, primary_key=True)
    ecole_id = db.Column(db.Integer, db.ForeignKey("ecoles.id"), index=True)  # vide : toutes les écoles
    titre = db.Column(db.String(150), nullable=False)
    contenu = db.Column(db.Text, nullable=False)
    public = db.Column(db.String(12), nullable=False, default="direction")  # direction | tous
    date_publication = db.Column(db.DateTime, nullable=False, default=maintenant)
    date_fin = db.Column(db.Date)  # plus affichée après cette date
    active = db.Column(db.Boolean, nullable=False, default=True)

    ecole = db.relationship("Ecole")
