from datetime import datetime

from app.extensions import db


class JournalAction(db.Model):
    """Trace centralisée des actions sensibles — qui, quoi, quand, sur
    quoi. Ne remplace pas les champs métier déjà existants
    (enregistre_par_id, responsable_id...), mais donne UN SEUL endroit où
    consulter l'historique complet, quel que soit le module (sept. 2026)."""
    __tablename__ = "journal_actions"

    id = db.Column(db.Integer, primary_key=True)
    utilisateur_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(60), nullable=False)
    details = db.Column(db.String(300))
    cible_type = db.Column(db.String(40))
    cible_id = db.Column(db.Integer)
    date_action = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    utilisateur = db.relationship("User")

    def __repr__(self):
        return f"<JournalAction {self.action} par {self.utilisateur_id}>"
