from app.extensions import db


class ParametreEtablissement(db.Model):
    """Réglages globaux de l'école — une seule ligne (id=1), pour des
    informations comme le nom de la personne à faire apparaître sur les
    documents officiels générés (sept. 2026)."""
    __tablename__ = "parametres_etablissement"

    id = db.Column(db.Integer, primary_key=True)
    nom_directeur = db.Column(db.String(120))
    titre_directeur = db.Column(db.String(120), default="Le Directeur / La Directrice")

    @staticmethod
    def get():
        parametre = ParametreEtablissement.query.get(1)
        if parametre is None:
            parametre = ParametreEtablissement(id=1)
            db.session.add(parametre)
            db.session.commit()
        return parametre
