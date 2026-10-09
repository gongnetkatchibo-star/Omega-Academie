from app.models.tenant import AppartientEcole
from datetime import datetime

from app.extensions import db
from app.services.temps import maintenant


STATUTS_DOSSIER = ["complet", "incomplet"]

# Raison du départ d'un élève (radiation). Un élève « sortant » au passage
# de classe n'a pas de motif enregistré : il est affiché comme tel.
MOTIFS_DEPART = [
    ("transfert", "Transfert vers une autre école"),
    ("abandon", "Abandon"),
    ("demenagement", "Déménagement de la famille"),
    ("exclusion", "Exclusion définitive"),
    ("fin_etudes", "Fin de scolarité"),
    ("autre", "Autre"),
]
LIBELLES_MOTIF_DEPART = dict(MOTIFS_DEPART)

# 1 élève → 1 ou 2 parents maximum (règle de la direction, sept. 2026).
MAX_PARENTS_PAR_ELEVE = 2

# Table d'association pure (pas de modèle dédié : aucune donnée propre à
# la relation elle-même, juste le lien élève↔parent).
eleve_parents = db.Table(
    "eleve_parents",
    db.Column("eleve_id", db.Integer, db.ForeignKey("eleves.id"), primary_key=True),
    db.Column("parent_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
)


class Eleve(AppartientEcole, db.Model):
    __tablename__ = "eleves"

    id = db.Column(db.Integer, primary_key=True)
    matricule = db.Column(db.String(30), unique=True, nullable=False)
    nom_complet = db.Column(db.String(120), nullable=False)
    date_naissance = db.Column(db.Date)
    sexe = db.Column(db.String(1))
    classe_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    telephone_parent = db.Column(db.String(30))
    # Dossier complet (facultatif, renseigné à l'inscription ou plus tard).
    lieu_naissance = db.Column(db.String(120))
    nationalite = db.Column(db.String(60))
    adresse = db.Column(db.String(200))
    nom_pere = db.Column(db.String(120))
    nom_mere = db.Column(db.String(120))
    personne_urgence = db.Column(db.String(120))
    telephone_urgence = db.Column(db.String(30))
    ecole_origine = db.Column(db.String(150))
    # Remise accordée sur la scolarité (bourse, fratrie, enfant du personnel…).
    remise_pourcent = db.Column(db.Float, default=0)
    remise_motif = db.Column(db.String(120))
    # Chargée seulement quand on l'affiche : sans cela, chaque liste
    # d'élèves ramènerait toutes les photos de la base.
    photo = db.deferred(db.Column(db.LargeBinary))
    photo_mime = db.Column(db.String(40))
    statut_dossier = db.Column(db.String(20), default="incomplet")
    date_inscription = db.Column(db.DateTime, default=maintenant)
    actif = db.Column(db.Boolean, default=True, nullable=False)
    # Départ de l'école (radiation) — vide tant que l'élève est inscrit.
    date_depart = db.Column(db.Date)
    motif_depart = db.Column(db.String(20))
    details_depart = db.Column(db.String(250))
    ecole_destination = db.Column(db.String(150))
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

    @property
    def libelle_motif_depart(self):
        if not self.motif_depart:
            return "Sortant (fin d'année)"
        return LIBELLES_MOTIF_DEPART.get(self.motif_depart, self.motif_depart)

    @staticmethod
    def annee_scolaire_courante():
        aujourd_hui = maintenant()
        if aujourd_hui.month >= 9:
            return f"{aujourd_hui.year}-{aujourd_hui.year + 1}"
        return f"{aujourd_hui.year - 1}-{aujourd_hui.year}"

    @classmethod
    def generer_matricule(cls, classe):
        """PREFIXE-CLASSE-XXX (numéro séquentiel à 3 chiffres, par classe).
        Le préfixe est celui de l'école (ex. OA26), modifiable dans les
        paramètres de l'établissement à chaque rentrée."""
        from flask import current_app
        from app.services.tenant import ecole_courante

        ecole = ecole_courante()
        prefixe = (ecole.prefixe_matricule if ecole else None) or current_app.config.get("MATRICULE_PREFIXE", "OA26")
        debut = f"{prefixe}-{classe.nom.upper()}-"
        # Numéro suivant le plus grand déjà attribué (et non « nombre
        # d'élèves + 1 », qui redonnait un matricule existant après un
        # changement de classe ou une suppression). Le matricule est
        # unique sur toute la plateforme : on regarde toutes les écoles.
        from sqlalchemy import select
        from app.models.classe import Classe

        # La classe est verrouillée jusqu'à la fin de l'inscription : deux
        # secrétaires qui inscrivent au même instant dans la même classe
        # obtiennent deux matricules différents (sans effet sur SQLite, où
        # les écritures se suivent déjà une à une).
        db.session.execute(select(Classe.id).where(Classe.id == classe.id).with_for_update())

        existants = db.session.execute(
            select(cls.matricule).where(cls.matricule.startswith(debut, autoescape=True))
            .execution_options(tous_etablissements=True)
        ).scalars().all()
        rangs = [int(m[len(debut):]) for m in existants if m[len(debut):].isdigit()]
        return f"{debut}{max(rangs, default=0) + 1:03d}"

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
