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
    # Bulletins, certificats, attestations et reçus en français et en
    # arabe côte à côte (oct. 2026).
    documents_bilingues = db.Column(db.Boolean, nullable=False, default=False)
    # Dates limites de paiement de l'année en cours ; au-delà, ce qui
    # reste dû sur l'échéance est compté en retard.
    date_limite_inscription = db.Column(db.Date)
    date_limite_tranche_1 = db.Column(db.Date)
    date_limite_tranche_2 = db.Column(db.Date)
    # Découpage de l'année (services/periodes.py) et cycles proposés à la
    # création des classes, en plus du primaire et du collège (oct. 2026).
    systeme_periodes = db.Column(db.String(20), nullable=False, default="trimestres")
    cycle_maternelle = db.Column(db.Boolean, nullable=False, default=False)
    cycle_lycee = db.Column(db.Boolean, nullable=False, default=False)

    @staticmethod
    def get():
        parametre = ParametreEtablissement.query.first()
        if parametre is None:
            parametre = ParametreEtablissement(titre_directeur="Directeur", genre_directeur="M")
            db.session.add(parametre)
            db.session.commit()
        return parametre
