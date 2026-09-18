from app.extensions import db


class Ecole(db.Model):
    __tablename__ = "ecoles"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    slogan = db.Column(db.String(200))
    couleur_principale = db.Column(db.String(7), default="#00387B")
    couleur_secondaire = db.Column(db.String(7), default="#DEA230")
    logo_path = db.Column(db.String(255))

    utilisateurs = db.relationship("User", back_populates="ecole")

    def __repr__(self):
        return f"<Ecole {self.nom}>"
