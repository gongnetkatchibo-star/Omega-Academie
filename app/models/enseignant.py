from app.extensions import db


class Enseignant(db.Model):
    __tablename__ = "enseignants"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    specialite = db.Column(db.String(120))

    user = db.relationship("User", backref=db.backref("profil_enseignant", uselist=False))
    affectations = db.relationship("Affectation", back_populates="enseignant", cascade="all, delete-orphan")

    @property
    def nom_complet(self):
        return self.user.nom_complet

    def __repr__(self):
        return f"<Enseignant {self.nom_complet}>"


class Affectation(db.Model):
    __tablename__ = "affectations"

    id = db.Column(db.Integer, primary_key=True)
    enseignant_id = db.Column(db.Integer, db.ForeignKey("enseignants.id"), nullable=False)
    classe_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    matiere = db.Column(db.String(80), nullable=False)

    enseignant = db.relationship("Enseignant", back_populates="affectations")
    classe = db.relationship("Classe")

    def __repr__(self):
        return f"<Affectation ens={self.enseignant_id} classe={self.classe_id} {self.matiere}>"
