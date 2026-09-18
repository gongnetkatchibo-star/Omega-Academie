from datetime import datetime

from app.extensions import db

TYPES_CAISSE = [
    "Uniforme",
    "Fournitures",
    "Salaire",
    "Loyer / Charges",
    "Transport",
    "Entretien",
    "Divers",
]

# Type réservé aux lignes générées automatiquement depuis Finances —
# n'apparaît jamais comme choix dans le formulaire de saisie manuelle.
TYPE_SCOLARITE_AUTO = "Scolarité (Finances)"


class MouvementCaisse(db.Model):
    __tablename__ = "mouvements_caisse"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    type = db.Column(db.String(60), nullable=False)
    reference = db.Column(db.String(60))
    libelle = db.Column(db.String(200), nullable=False)
    recette = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    depense = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    observation = db.Column(db.String(300))
    responsable_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    date_saisie = db.Column(db.DateTime, default=datetime.utcnow)

    # Traçabilité vers l'élève concerné quand la ligne vient d'un paiement
    # de scolarité — les parents se retrouvent via eleve.parents (pas
    # besoin de dupliquer l'information, elle resterait à jour automatiquement).
    eleve_id = db.Column(db.Integer, db.ForeignKey("eleves.id"))

    # Traçabilité générique : quand une ligne est générée automatiquement
    # par un autre module (Finances aujourd'hui ; un futur module de
    # dépenses — salaires, achats — pourra suivre le même principe sans
    # changer ce modèle). Une ligne automatique ne se modifie/supprime
    # jamais depuis l'écran Caisse : on corrige à la source.
    origine_module = db.Column(db.String(30))
    origine_id = db.Column(db.Integer)
    automatique = db.Column(db.Boolean, default=False, nullable=False)

    responsable = db.relationship("User", foreign_keys=[responsable_id])
    eleve = db.relationship("Eleve")

    def __repr__(self):
        return f"<MouvementCaisse {self.date} {self.libelle}>"
