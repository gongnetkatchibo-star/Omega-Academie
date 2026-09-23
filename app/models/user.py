from datetime import datetime, timedelta

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db

ROLES = [
    "developpeur",
    "super_administrateur",
    "fondateur",
    "administrateur_general",
    "directeur_primaire",
    "directeur_college",
    "secretaire",
    "comptable",
    "responsable_pedagogique",
    "bibliothecaire",
    "personnel",
    "enseignant",
    "eleve",
    "parent",
]

# Rôles dont on considère qu'ils font partie de la direction / administration
# générale de l'école (accès large aux modules de gestion).
ROLES_DIRECTION = [
    "fondateur", "administrateur_general", "directeur_primaire", "directeur_college",
    "super_administrateur",
]

# Un directeur de cycle (contrairement à fondateur/administrateur_general) est
# restreint à ses propres classes — voir app/services/cycles.py.
ROLES_DIRECTEUR_CYCLE = ["directeur_primaire", "directeur_college"]

# Rôles de personnel administratif / support (accès plus ciblé, un module chacun).
ROLES_PERSONNEL = ["secretaire", "comptable", "responsable_pedagogique", "bibliothecaire", "personnel"]

STATUTS = ["en_attente", "actif", "refuse", "verrouille"]


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    nom_complet = db.Column(db.String(120), nullable=False)
    prenom = db.Column(db.String(60))
    nom = db.Column(db.String(60))
    profession = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    telephone = db.Column(db.String(30), unique=True, index=True)
    genre = db.Column(db.String(1))
    mot_de_passe_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(40), nullable=False)
    statut = db.Column(db.String(20), nullable=False, default="en_attente")
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    ecole_id = db.Column(db.Integer, db.ForeignKey("ecoles.id"))
    ecole = db.relationship("Ecole", back_populates="utilisateurs")

    # Vérification de l'email — code à usage unique envoyé une seule fois,
    # à l'inscription (pas à chaque connexion, décision de la direction,
    # sept. 2026). Les mêmes colonnes/méthodes servent pour ça.
    code_2fa = db.Column(db.String(6))
    code_2fa_expiration = db.Column(db.DateTime)
    email_verifie = db.Column(db.Boolean, default=False, nullable=False)

    def set_mot_de_passe(self, mot_de_passe):
        self.mot_de_passe_hash = generate_password_hash(mot_de_passe)

    def verifier_mot_de_passe(self, mot_de_passe):
        return check_password_hash(self.mot_de_passe_hash, mot_de_passe)

    def generer_code_2fa(self):
        import random
        self.code_2fa = f"{random.randint(0, 999999):06d}"
        self.code_2fa_expiration = datetime.utcnow() + timedelta(minutes=10)
        return self.code_2fa

    def verifier_code_2fa(self, code):
        if not self.code_2fa or not self.code_2fa_expiration:
            return False
        if datetime.utcnow() > self.code_2fa_expiration:
            return False
        return code.strip() == self.code_2fa

    def invalider_code_2fa(self):
        self.code_2fa = None
        self.code_2fa_expiration = None

    @property
    def is_active(self):
        # Redéfinit UserMixin.is_active : un compte "en_attente" ou "refuse"
        # ne peut pas se connecter tant que le secrétaire ne l'a pas approuvé.
        return self.statut == "actif"

    def __repr__(self):
        return f"<User {self.email} ({self.role}, {self.statut})>"
