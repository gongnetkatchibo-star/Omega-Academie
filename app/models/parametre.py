from app.extensions import db


class ParametreEtablissement(db.Model):
    """Réglages globaux de l'école (une seule ligne, id=1) : signataire
    proposé par défaut sur les documents générés."""
    __tablename__ = "parametres_etablissement"

    id = db.Column(db.Integer, primary_key=True)
    nom_directeur = db.Column(db.String(120))
    titre_directeur = db.Column(db.String(120), default="Directeur")
    genre_directeur = db.Column(db.String(1), default="M")

    @staticmethod
    def get():
        parametre = db.session.get(ParametreEtablissement, 1)
        if parametre is None:
            parametre = ParametreEtablissement(id=1, titre_directeur="Directeur", genre_directeur="M")
            db.session.add(parametre)
            db.session.commit()
        return parametre
