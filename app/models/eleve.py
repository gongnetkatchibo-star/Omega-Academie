from datetime import datetime

from app.extensions import db


STATUTS_DOSSIER = ["complet", "incomplet"]

# 1 élève → 1 ou 2 parents maximum (règle de la direction, sept. 2026).
MAX_PARENTS_PAR_ELEVE = 2

# Table d'association pure (pas de modèle dédié : aucune donnée propre à
# la relation elle-même, juste le lien élève↔parent).
eleve_parents = db.Table(
    "eleve_parents",
    db.Column("eleve_id", db.Integer, db.ForeignKey("eleves.id"), primary_key=True),
    db.Column("parent_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
)


class Eleve(db.Model):
    __tablename__ = "eleves"

    id = db.Column(db.Integer, primary_key=True)
    matricule = db.Column(db.String(30), unique=True, nullable=False)
    nom_complet = db.Column(db.String(120), nullable=False)
    date_naissance = db.Column(db.Date)
    sexe = db.Column(db.String(1))
    classe_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    telephone_parent = db.Column(db.String(30))
    statut_dossier = db.Column(db.String(20), default="incomplet")
    date_inscription = db.Column(db.DateTime, default=datetime.utcnow)
    actif = db.Column(db.Boolean, default=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True)

    classe = db.relationship("Classe", back_populates="eleves")
    # 1 élève → jusqu'à 2 parents ; 1 parent → plusieurs élèves (via
    # `User.enfants`, le backref ci-dessous).
    parents = db.relationship("User", secondary=eleve_parents, backref="enfants")
    compte = db.relationship("User", foreign_keys=[user_id])
    historique = db.relationship(
        "HistoriqueScolaire", back_populates="eleve", order_by="HistoriqueScolaire.id"
    )
    paiements = db.relationship("Paiement", back_populates="eleve")

    @staticmethod
    def annee_scolaire_courante():
        aujourd_hui = datetime.utcnow()
        if aujourd_hui.month >= 9:
            return f"{aujourd_hui.year}-{aujourd_hui.year + 1}"
        return f"{aujourd_hui.year - 1}-{aujourd_hui.year}"

    @classmethod
    def generer_matricule(cls, classe):
        """Format officiel 2026-2027 fourni par la direction :
        OA26-CLASSE-XXX (numéro séquentiel à 3 chiffres, par classe).
        Le préfixe est fixe pour l'année en cours ; il devra être mis à
        jour (ex. OA27) à la rentrée suivante — voir config.py."""
        from flask import current_app

        prefixe = current_app.config.get("MATRICULE_PREFIXE", "OA26")
        code_classe = classe.nom.upper()
        rang = cls.query.filter_by(classe_id=classe.id).count() + 1
        return f"{prefixe}-{code_classe}-{rang:03d}"

    def dossier_est_complet(self):
        """Un dossier est complet quand toutes les informations
        essentielles sont réunies : identité, classe, au moins un parent
        lié, et un téléphone de contact (le sien ou celui d'un parent).
        Recalculé automatiquement — jamais coché à la main (décision de
        la direction, sept. 2026)."""
        return bool(
            self.date_naissance
            and self.sexe
            and self.classe_id
            and self.parents
            and (self.telephone_parent or any(p.telephone for p in self.parents))
        )

    def actualiser_statut_dossier(self):
        self.statut_dossier = "complet" if self.dossier_est_complet() else "incomplet"

    def __repr__(self):
        return f"<Eleve {self.matricule} {self.nom_complet}>"
