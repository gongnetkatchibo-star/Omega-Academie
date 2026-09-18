from app.extensions import db


class Classe(db.Model):
    __tablename__ = "classes"
    __table_args__ = (
        # Un même nom (ex. "CP1") peut exister sur plusieurs années
        # scolaires différentes — chaque année a sa propre ligne, ce qui
        # permet de conserver et consulter les années précédentes
        # (document complémentaire, sept. 2026). Il ne peut simplement pas
        # y avoir deux fois "CP1" pour la MÊME année.
        db.UniqueConstraint("nom", "annee_scolaire", name="uq_classe_nom_annee"),
    )

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(20), nullable=False)
    niveau = db.Column(db.Integer, nullable=False)  # ordre pour le passage de classe
    annee_scolaire = db.Column(db.String(9), nullable=False)

    # Échéancier officiel 2026-2027 (fiche du fondateur) : les frais se
    # payent en 3 échéances distinctes, chacune avec son propre montant.
    frais_inscription = db.Column(db.Float, default=0)
    frais_tranche1 = db.Column(db.Float, default=0)
    frais_tranche2 = db.Column(db.Float, default=0)

    eleves = db.relationship("Eleve", back_populates="classe", lazy="dynamic")

    @property
    def frais_annuel(self):
        """Total annuel = somme des 3 échéances (remplace l'ancien champ
        stocké directement ; conservé en lecture seule pour ne pas casser
        le reste du code qui affiche un total)."""
        return (self.frais_inscription or 0) + (self.frais_tranche1 or 0) + (self.frais_tranche2 or 0)

    def __repr__(self):
        return f"<Classe {self.nom}>"
