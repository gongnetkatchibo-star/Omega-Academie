from app.models.tenant import AppartientEcole
from app.extensions import db
from app.services.temps import maintenant, aujourd_hui


class Livre(AppartientEcole, db.Model):
    """Livre papier de la bibliothèque de l'école (les livres numériques
    sont des Ressource)."""

    __tablename__ = "livres"

    id = db.Column(db.Integer, primary_key=True)
    titre = db.Column(db.String(200), nullable=False)
    auteur = db.Column(db.String(150))
    cote = db.Column(db.String(40))          # numéro ou étiquette collée sur le livre
    categorie = db.Column(db.String(80))
    exemplaires = db.Column(db.Integer, nullable=False, default=1)
    date_ajout = db.Column(db.DateTime, default=maintenant)

    prets = db.relationship("Pret", back_populates="livre", order_by="Pret.date_pret.desc()")

    @property
    def prets_en_cours(self):
        return [p for p in self.prets if p.date_retour is None]

    @property
    def disponibles(self):
        return max(self.exemplaires - len(self.prets_en_cours), 0)

    def __repr__(self):
        return f"<Livre {self.titre}>"


class Pret(AppartientEcole, db.Model):
    """Un exemplaire prêté à un élève ou à un membre du personnel."""

    __tablename__ = "prets"

    id = db.Column(db.Integer, primary_key=True)
    livre_id = db.Column(db.Integer, db.ForeignKey("livres.id"), nullable=False, index=True)
    eleve_id = db.Column(db.Integer, db.ForeignKey("eleves.id"), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    date_pret = db.Column(db.Date, nullable=False)
    date_retour_prevue = db.Column(db.Date, nullable=False)
    date_retour = db.Column(db.Date)
    remarque = db.Column(db.String(200))
    prete_par_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    date_creation = db.Column(db.DateTime, default=maintenant)

    livre = db.relationship("Livre", back_populates="prets")
    eleve = db.relationship("Eleve")
    emprunteur_personnel = db.relationship("User", foreign_keys=[user_id])
    prete_par = db.relationship("User", foreign_keys=[prete_par_id])

    @property
    def nom_emprunteur(self):
        if self.eleve:
            return self.eleve.nom_complet
        return self.emprunteur_personnel.nom_complet if self.emprunteur_personnel else "—"

    @property
    def en_retard(self):
        return self.date_retour is None and self.date_retour_prevue < aujourd_hui()

    def __repr__(self):
        return f"<Pret livre={self.livre_id} {self.date_pret}>"
