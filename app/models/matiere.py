from app.models.tenant import AppartientEcole
from app.extensions import db


class MatiereEcole(AppartientEcole, db.Model):
    """Liste officielle des matières d'une école (facultative). Vide, les
    matières restent saisies librement, comme avant ; remplie, elles se
    choisissent dans cette liste (affectations, emplois du temps)."""

    __tablename__ = "matieres_ecole"
    __table_args__ = (db.UniqueConstraint("ecole_id", "nom", name="uq_matiere_ecole_nom"),)

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(80), nullable=False)
    ordre = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<MatiereEcole {self.nom}>"


def matieres_officielles():
    """Noms des matières de l'école, dans l'ordre choisi ([] sans liste)."""
    return [m.nom for m in MatiereEcole.query.order_by(MatiereEcole.ordre, MatiereEcole.nom).all()]


def matiere_acceptee(nom):
    """Une matière saisie est-elle valable pour l'école ? Toujours vrai
    sans liste officielle."""
    liste = matieres_officielles()
    return not liste or nom in liste
