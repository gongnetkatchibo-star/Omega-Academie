from app.models.tenant import AppartientEcole
from app.extensions import db


class ParametreEtablissement(AppartientEcole, db.Model):
    """Réglages propres à chaque école : signataire proposé par défaut
    sur les documents générés (une ligne par école)."""
    __tablename__ = "parametres_etablissement"

    id = db.Column(db.Integer, primary_key=True)
    nom_directeur = db.Column(db.String(120))
    titre_directeur = db.Column(db.String(120), default="Directeur")
    genre_directeur = db.Column(db.String(1), default="M")

    @staticmethod
    def get():
        parametre = ParametreEtablissement.query.first()
        if parametre is None:
            parametre = ParametreEtablissement(titre_directeur="Directeur", genre_directeur="M")
            db.session.add(parametre)
            db.session.commit()
        return parametre
