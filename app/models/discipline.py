from app.models.tenant import AppartientEcole
from app.extensions import db
from app.services.temps import maintenant

TYPES_INCIDENT = [
    ("retard", "Retard"),
    ("avertissement", "Avertissement"),
    ("blame", "Blâme"),
    ("convocation", "Convocation des parents"),
    ("exclusion", "Exclusion temporaire"),
    ("autre", "Autre"),
]
LIBELLES_INCIDENT = dict(TYPES_INCIDENT)


class Incident(AppartientEcole, db.Model):
    """Retard ou fait de discipline d'un élève, avec la suite donnée."""

    __tablename__ = "incidents"

    id = db.Column(db.Integer, primary_key=True)
    eleve_id = db.Column(db.Integer, db.ForeignKey("eleves.id"), nullable=False, index=True)
    classe_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    type = db.Column(db.String(20), nullable=False)
    motif = db.Column(db.String(250))
    minutes = db.Column(db.Integer)       # retard
    duree_jours = db.Column(db.Integer)   # exclusion temporaire
    auteur_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    date_creation = db.Column(db.DateTime, default=maintenant)

    eleve = db.relationship("Eleve")
    classe = db.relationship("Classe")
    auteur = db.relationship("User")

    @property
    def libelle(self):
        return LIBELLES_INCIDENT.get(self.type, self.type)

    def __repr__(self):
        return f"<Incident {self.type} eleve={self.eleve_id} {self.date}>"
