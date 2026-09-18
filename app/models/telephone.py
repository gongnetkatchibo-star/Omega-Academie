from app.extensions import db

OPERATEURS_TCHAD = [("airtel", "Airtel Tchad"), ("moov", "Moov Africa Tchad")]


class NumeroTelephone(db.Model):
    """Un utilisateur peut avoir plusieurs numéros (principal, autre
    membre de la famille joignable, etc.) — pour être contacté en dehors
    de l'application, par exemple par SMS plus tard (sept. 2026)."""
    __tablename__ = "numeros_telephone"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    numero = db.Column(db.String(20), nullable=False)  # stocké sous forme +235XXXXXXXX
    operateur = db.Column(db.String(10), nullable=False)  # "airtel" ou "moov"
    libelle = db.Column(db.String(40))  # ex. "Principal", "Papa", "Bureau"

    utilisateur = db.relationship("User", backref="numeros_telephone")

    def __repr__(self):
        return f"<NumeroTelephone {self.numero} ({self.operateur})>"
