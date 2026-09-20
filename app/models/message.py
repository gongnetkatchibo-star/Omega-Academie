from datetime import datetime

from app.extensions import db


class Message(db.Model):
    """Fil de discussion simple entre un parent et l'école — tous les
    messages liés à un même parent_id forment un seul fil, que ce soit
    le parent ou un membre du personnel qui écrit (sept. 2026)."""
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    auteur_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    contenu = db.Column(db.Text, nullable=False)
    date_envoi = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    lu_par_ecole = db.Column(db.Boolean, default=False, nullable=False)
    lu_par_parent = db.Column(db.Boolean, default=False, nullable=False)

    parent = db.relationship("User", foreign_keys=[parent_id])
    auteur = db.relationship("User", foreign_keys=[auteur_id])

    def __repr__(self):
        return f"<Message de {self.auteur_id} pour le fil de {self.parent_id}>"
