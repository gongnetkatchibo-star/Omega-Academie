from datetime import datetime

from app.extensions import db
from app.services.temps import maintenant


class Ecole(db.Model):
    """Un établissement scolaire hébergé sur la plateforme. Toutes les
    données métier (élèves, notes, paiements...) portent un ecole_id et
    ne sont visibles que depuis leur propre établissement."""
    __tablename__ = "ecoles"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    sigle = db.Column(db.String(20))
    ville = db.Column(db.String(80))
    pays = db.Column(db.String(80))
    slogan = db.Column(db.String(200))  # devise affichée dans la barre du haut
    # Nom et ville en arabe, pour l'en-tête des documents bilingues (oct. 2026).
    nom_arabe = db.Column(db.String(200))
    ville_arabe = db.Column(db.String(80))
    prefixe_matricule = db.Column(db.String(20), unique=True)
    # Mot court du lien propre à l'école : https://…/e/<identifiant>
    # (services/liens_ecole.py). Unique ; attribué à la création.
    identifiant = db.Column(db.String(60), unique=True, index=True)
    # Campagne de pré-inscription : fermée, le formulaire public n'est
    # pas accessible, même avec son lien. L'administration de l'école
    # l'ouvre le temps de la campagne et partage alors le lien.
    preinscriptions_ouvertes = db.Column(db.Boolean, nullable=False, default=False)
    couleur_principale = db.Column(db.String(7), default="#00387B")
    couleur_secondaire = db.Column(db.String(7), default="#DEA230")
    # Couleurs de l'interface choisies par l'école (oct. 2026). Vides : les
    # couleurs de la plateforme. Les deux colonnes ci-dessus, plus
    # anciennes, ne sont pas utilisées par l'interface.
    couleur_theme = db.Column(db.String(7))
    couleur_accent = db.Column(db.String(7))
    # Code envoyé par email à chaque connexion de la direction et de la
    # comptabilité (sauf sur un appareil de confiance).
    double_authentification = db.Column(db.Boolean, nullable=False, default=False)
    logo_path = db.Column(db.String(255))
    logo = db.Column(db.LargeBinary)
    logo_mime = db.Column(db.String(50))
    filigrane = db.Column(db.LargeBinary)
    filigrane_mime = db.Column(db.String(50))
    actif = db.Column(db.Boolean, default=True, nullable=False)
    date_creation = db.Column(db.DateTime, default=maintenant)

    utilisateurs = db.relationship("User", back_populates="ecole")

    @property
    def devise(self):
        return self.slogan

    @property
    def nom_officiel(self):
        return (self.nom or "").upper()

    def __repr__(self):
        return f"<Ecole {self.nom}>"
