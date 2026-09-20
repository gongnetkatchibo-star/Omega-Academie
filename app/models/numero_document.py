from app.extensions import db


class NumeroDocument(db.Model):
    """Compteur séquentiel par type de document et par année — garantit
    que deux documents n'ont jamais le même numéro de référence, même en
    cas d'utilisation simultanée par deux personnes (sept. 2026)."""
    __tablename__ = "numeros_documents"
    __table_args__ = (
        db.UniqueConstraint("type_document", "annee", name="uq_numero_document_type_annee"),
    )

    id = db.Column(db.Integer, primary_key=True)
    type_document = db.Column(db.String(20), nullable=False)  # ex. "CERT", "ATTEST", "DEC"
    annee = db.Column(db.Integer, nullable=False)
    dernier_numero = db.Column(db.Integer, nullable=False, default=0)
