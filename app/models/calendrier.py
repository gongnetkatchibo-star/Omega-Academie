from app.models.tenant import AppartientEcole
from app.extensions import db
from app.services.temps import maintenant

TYPES_EVENEMENT = [
    ("rentree", "Rentrée"),
    ("vacances", "Vacances"),
    ("ferie", "Jour férié"),
    ("examen", "Compositions et examens"),
    ("reunion", "Réunion"),
    ("evenement", "Événement"),
]
LIBELLES_EVENEMENT = dict(TYPES_EVENEMENT)


class EvenementCalendrier(AppartientEcole, db.Model):
    """Date du calendrier scolaire : vacances, jours fériés, compositions,
    réunions de parents…"""

    __tablename__ = "evenements_calendrier"

    id = db.Column(db.Integer, primary_key=True)
    titre = db.Column(db.String(150), nullable=False)
    type = db.Column(db.String(20), nullable=False, default="evenement")
    date_debut = db.Column(db.Date, nullable=False, index=True)
    date_fin = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(500))
    # Faux : réservé au personnel (conseil de classe, réunion pédagogique…).
    visible_familles = db.Column(db.Boolean, nullable=False, default=True)
    date_creation = db.Column(db.DateTime, default=maintenant)

    @property
    def libelle(self):
        return LIBELLES_EVENEMENT.get(self.type, self.type)

    @property
    def sur_un_jour(self):
        return self.date_debut == self.date_fin

    def __repr__(self):
        return f"<Evenement {self.titre} {self.date_debut}>"
