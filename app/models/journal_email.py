from datetime import datetime

from app.extensions import db


class JournalEmail(db.Model):
    """Trace de chaque email que l'application a tenté d'envoyer — pour
    pouvoir vérifier après coup ce qui est réellement parti en cas de
    réclamation ("je n'ai rien reçu") ou d'incident (sept. 2026)."""
    __tablename__ = "journal_emails"

    id = db.Column(db.Integer, primary_key=True)
    destinataires = db.Column(db.String(500), nullable=False)  # séparés par des virgules
    sujet = db.Column(db.String(200), nullable=False)
    reussi = db.Column(db.Boolean, nullable=False)
    date_envoi = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<JournalEmail {self.sujet} -> {self.destinataires} ({'OK' if self.reussi else 'échec'})>"
