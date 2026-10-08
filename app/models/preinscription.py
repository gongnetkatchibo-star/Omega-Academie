from app.models.tenant import AppartientEcole
from app.extensions import db
from app.services.temps import maintenant

STATUTS_PREINSCRIPTION = [
    ("nouvelle", "Nouvelle"),
    ("convoquee", "Convoqué au test"),
    ("refusee", "Refusée"),
]
LIBELLES_STATUT_PREINSCRIPTION = dict(STATUTS_PREINSCRIPTION)


class PreInscription(AppartientEcole, db.Model):
    """Demande déposée en ligne par une famille, depuis la page publique ;
    le secrétariat la convoque au test de niveau ou la refuse."""

    __tablename__ = "preinscriptions"

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(20), unique=True, nullable=False)
    nom_candidat = db.Column(db.String(120), nullable=False)
    sexe = db.Column(db.String(1))
    date_naissance = db.Column(db.Date)
    lieu_naissance = db.Column(db.String(120))
    classe_demandee_id = db.Column(db.Integer, db.ForeignKey("classes.id"))
    ecole_origine = db.Column(db.String(150))
    nom_parent = db.Column(db.String(120), nullable=False)
    telephone_parent = db.Column(db.String(30), nullable=False)
    email_parent = db.Column(db.String(150))
    message = db.Column(db.String(1000))
    statut = db.Column(db.String(20), nullable=False, default="nouvelle")
    motif_refus = db.Column(db.String(250))
    test_niveau_id = db.Column(db.Integer, db.ForeignKey("tests_niveau.id"))
    traite_par_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    date_creation = db.Column(db.DateTime, default=maintenant)

    classe_demandee = db.relationship("Classe")
    test_niveau = db.relationship("TestNiveau")
    traite_par = db.relationship("User")

    @property
    def libelle_statut(self):
        return LIBELLES_STATUT_PREINSCRIPTION.get(self.statut, self.statut)

    def __repr__(self):
        return f"<PreInscription {self.reference} {self.nom_candidat}>"
